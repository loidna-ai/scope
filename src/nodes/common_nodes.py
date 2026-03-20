"""
공통 노드 정의
모든 전문가가 공통으로 사용하는 노드들

- hotspot_detector_node: [Overlap Grid] 이미지 패치 분할 → Gemini 병렬 분석 → NMS 중복 제거
- _update_image_path_in_result: 결과에 image_path 업데이트 헬퍼
"""
import asyncio
import os
from pathlib import Path
from typing import Any, Dict

from google.genai import types

from src.models.hotspot_models import HotspotDetectionResult
from src.prompts.common_prompts import get_micro_evidence_prompt
from src.state import InvestigationState
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file
from src.utils import async_retry_with_backoff, get_genai_client
from src.utils.image_processing import (
    get_image_size, 
    slice_multiple_images, 
    map_hotspots_to_global, 
    perform_batch_nms
)
from src.utils.logging_config import setup_logger

from src.utils.expert_config import get_safety_settings
from src.utils.api_concurrency import batch_process_hotspots
from src.utils.identity_fusion import run_identity_fusion

logger = setup_logger("common_nodes")

# === Hotspot Detector: 전역 Rate Limit/Semaphore 사용 (src.utils.api_concurrency) ===
# async_retry_with_backoff 내부에서 acquire_api_slot()으로 통합 제어
import config


def _update_image_path_in_result(
    result: Dict[str, Any],
    temp_image_path: str,
    existing_image_path: str | None = None,
) -> None:
    """
    결과 딕셔너리에 image_path를 업데이트하는 헬퍼 함수
    임시 파일을 생성한 경우에만 업로드 (중복 제거)
    
    Args:
        result: 업데이트할 결과 딕셔너리
        temp_image_path: 새로 생성된 임시 파일 경로
        existing_image_path: 기존 image_path (없으면 None)
    """
    if not temp_image_path:
        return
    
    try:
        # 경로 비교: os.path.samefile 사용 (심볼릭 링크, 대소문자 차이 등 고려)
        if not existing_image_path or not os.path.exists(existing_image_path) or not os.path.samefile(temp_image_path, existing_image_path):
            result["image_path"] = temp_image_path
            logger.debug(f"Hotspot Detector: Updated image_path in State: {temp_image_path}")
    except (OSError, ValueError):
        # samefile 실패 시 (파일이 없거나 경로 문제) 단순 비교
        if not existing_image_path or temp_image_path != existing_image_path:
            result["image_path"] = temp_image_path
            logger.debug(f"Hotspot Detector: Updated image_path in State: {temp_image_path}")


async def hotspot_detector_node(state: InvestigationState) -> Dict[str, Any]:
    """
    [Overlap Grid Strategy] Hotspot Detector Node
    
    1. 슬라이싱: 이미지를 고해상도 패치로 분할 (Overlap 적용)
    2. 병렬 처리: 각 패치를 독립적으로 Gemini API에 전송 (Async)
    3. 종합: 결과를 수집하고 좌표를 전역 공간으로 매핑
    4. 중복 제거: NMS 알고리즘으로 겹치는 Hotspot 병합
    """
    # [인증 검증] Vertex AI 또는 Google AI Studio Client 획득
    try:
        client = get_genai_client()
    except ValueError as e:
        logger.error(f"Hotspot Detector: {e}")
        return {"hotspots": [], "errors": [str(e)]}
    
    # [Memory Optimization] 다중 이미지 처리 (image_paths 우선)
    image_paths = state.get("image_paths") or []
    
    if not image_paths:
        single_path = state.get("image_path")
        if single_path and os.path.exists(single_path):
            image_paths = [single_path]
            logger.info(f"Hotspot Detector: Using single existing image path: {single_path}")
        else:
            payload = state.get("payload", [])
            if not payload:
                error_msg = "Hotspot Detector: No payload and no image paths available."
                logger.warning(error_msg)
                return {"hotspots": [], "errors": [error_msg]}
            
            from src.tools.experts.expert_utils import extract_images_from_payload
            image_data_list = extract_images_from_payload(payload)
            if not image_data_list:
                error_msg = "Hotspot Detector: Failed to extract images from payload."
                logger.warning(error_msg)
                return {"hotspots": [], "errors": [error_msg]}
                
            image_paths = [save_bytes_to_temp_file(img) for img in image_data_list if img]
            
    if not image_paths:
        return {"hotspots": [], "errors": ["No images could be loaded."]}
    
    # 대표/첫 번째 이미지 경로 보존
    primary_image_path = image_paths[0]
    
    try:
        # 1. Image Slicing (모든 이미지에 대해 패치 생성)
        all_patches = slice_multiple_images(
            image_paths,
            patch_size=config.HOTSPOT_PATCH_SIZE,
            overlap=config.HOTSPOT_OVERLAP,
            max_dimension=config.HOTSPOT_MAX_IMAGE_DIMENSION,
            blur_threshold=config.HOTSPOT_BLUR_THRESHOLD,
            edge_threshold=config.HOTSPOT_EDGE_THRESHOLD
        )
        
        total_patches = len(all_patches)
        if total_patches == 0:
             logger.warning("Hotspot Detector: Image slicing resulted in 0 valid patches.")
             result = {"hotspots": [], "corrected_total_count": 0, "analysis_status": "NO_HOTSPOTS_DETECTED"}
             _update_image_path_in_result(result, primary_image_path, state.get("image_path"))
             return result

        # 2. Parallel API Execution (Group patches into batches)
        batch_size = getattr(config, 'HOTSPOT_BATCH_SIZE', 5)
        patch_batches = [all_patches[i:i + batch_size] for i in range(0, total_patches, batch_size)]
        
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        prompt = get_micro_evidence_prompt(config.HOTSPOT_PATCH_SIZE)
        
        json_schema = HotspotDetectionResult.model_json_schema()
        req = json_schema.setdefault("required", [])
        if "hotspots" not in req: req.append("hotspots")
        
        api_config = {
            "response_mime_type": "application/json",
            "response_json_schema": json_schema,
            "safety_settings": get_safety_settings(),
        }

        # API 호출 위임
        batch_results = await batch_process_hotspots(
            client=client,
            patch_batches=patch_batches,
            model_name=model_name,
            prompt=prompt,
            api_config=api_config
        )
        
        # 3. Aggregation & Coordinate Mapping
        image_sizes = {path: get_image_size(path) for path in image_paths}
        raw_hotspots = map_hotspots_to_global(batch_results, image_sizes)
        
        logger.info(f"Hotspot Detector: {len(raw_hotspots)} raw hotspots detected.")
        
        # [Debug Log] 상세 좌표 출력
        for i, hs in enumerate(raw_hotspots):
            comp = hs.get("component_name", "Unknown")
            conf = hs.get("confidence_score", 0.0)
            box = hs.get("box_2d", [0,0,0,0])
            # box_2d가 dict인 경우와 list인 경우 모두 대응
            if isinstance(box, dict):
                coords = f"[ymin:{box.get('ymin')}, xmin:{box.get('xmin')}, ymax:{box.get('ymax')}, xmax:{box.get('xmax')}]"
            else:
                coords = str(box)
            logger.info(f"  - Raw HS #{i}: {comp} (conf: {conf:.2f}) {coords}")
        
        # 4. Deduplication (NMS)
        final_raw_hotspots = perform_batch_nms(raw_hotspots, config.HOTSPOT_NMS_IOU_THRESHOLD)
        
        if not final_raw_hotspots:
            logger.warning("Hotspot Detector: No hotspots remaining after NMS.")
            result = {"hotspots": [], "corrected_total_count": 0, "analysis_status": "NO_HOTSPOTS_DETECTED"}
            _update_image_path_in_result(result, primary_image_path, state.get("image_path"))
            return result
                
        # 5. Identity Fusion (다중 뷰 객체 병합)
        unified_hotspots = await run_identity_fusion(client, image_paths, final_raw_hotspots)
        
        # State Update
        result = {
            "hotspots": unified_hotspots,
            "corrected_total_count": len(unified_hotspots),
            "analysis_status": "DETECTED",
        }
        _update_image_path_in_result(result, primary_image_path, state.get("image_path"))
        
        return result

    except Exception as e:
        error_msg = f"Hotspot Detector: Global Error: {e}"
        logger.error(error_msg, exc_info=True)
        result = {
            "hotspots": [],
            "errors": [error_msg],
            "analysis_status": "ERROR",
        }
        safe_image_path = image_paths[0] if image_paths else state.get("image_path")
        _update_image_path_in_result(result, safe_image_path, state.get("image_path"))
        return result
