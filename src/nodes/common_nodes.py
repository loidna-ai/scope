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
from src.utils.image_processing import get_image_size, map_box_to_global, slice_image
from src.utils.logging_config import setup_logger
from src.utils.nms import non_max_suppression
from src.utils.expert_config import get_safety_settings

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
    
    # [Memory Optimization] image_path 우선 사용
    image_path = state.get("image_path")
    temp_image_path = None
    
    if image_path and os.path.exists(image_path):
        logger.info(f"Hotspot Detector: Using existing image path: {image_path}")
        temp_image_path = image_path
    else:
        # Fallback: payload 사용 (기존 로직)
        payload = state.get("payload", [])
        if not payload:
            error_msg = "Hotspot Detector: No payload and no image path available."
            logger.warning(error_msg)
            return {"hotspots": [], "errors": [error_msg]}
        
        image_data = extract_image_from_payload(payload)
        if image_data is None:
            error_msg = "Hotspot Detector: Failed to extract image from payload."
            logger.warning(error_msg)
            return {"hotspots": [], "errors": [error_msg]}
            
        temp_image_path = save_bytes_to_temp_file(image_data)
        # Note: 임시 파일은 후속 노드에서 사용되므로 여기서 삭제하지 않음
    
    try:
        # 1. Image Slicing (config에서 파라미터 참조 및 필터링)
        logger.info(f"Hotspot Detector: Slicing image {temp_image_path} with Dynamic Resizing and OpenCV Filtering (Thresholds - Blur: {config.HOTSPOT_BLUR_THRESHOLD}, Edge: {config.HOTSPOT_EDGE_THRESHOLD})...")
        
        # slice_image는 이제 Generator를 반환 (안에서 OpenCV 배경 필터링 + 리사이즈 진행됨)
        patch_generator = slice_image(
            temp_image_path, 
            patch_size=config.HOTSPOT_PATCH_SIZE, 
            overlap=config.HOTSPOT_OVERLAP,
            max_dimension=config.HOTSPOT_MAX_IMAGE_DIMENSION,
            blur_threshold=config.HOTSPOT_BLUR_THRESHOLD,
            edge_threshold=config.HOTSPOT_EDGE_THRESHOLD
        )
        
        # 2. 패치 수집 및 Batch 구성 (Gemini Multi-image 특성 활용)
        patches_list = list(patch_generator)
        total_patches = len(patches_list)
        
        if total_patches == 0:
             logger.warning("Hotspot Detector: Image slicing resulted in 0 valid patches after OpenCV filtering.")
             result = {"hotspots": [], "corrected_total_count": 0, "analysis_status": "NO_HOTSPOTS_DETECTED"}
             _update_image_path_in_result(result, temp_image_path, image_path)
             return result

        batch_size = getattr(config, 'HOTSPOT_BATCH_SIZE', 5)
        # 패치들을 batch_size 단위의 청크로 분리
        patch_batches = [patches_list[i:i + batch_size] for i in range(0, len(patches_list), batch_size)]
        
        logger.info(f"Hotspot Detector: {total_patches} patches survived filtering. Grouping into {len(patch_batches)} batches (Max {batch_size} patches per API call) for Gemini Multi-Image processing...")
        
        # Parallel API Execution setup
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        prompt = get_micro_evidence_prompt(config.HOTSPOT_PATCH_SIZE)
        safety_settings_block_none = get_safety_settings()
        
        # Pydantic Schema
        json_schema = HotspotDetectionResult.model_json_schema()
        req = json_schema.setdefault("required", [])
        if "hotspots" not in req:
            req.append("hotspots")
        
        api_config = {
            "response_mime_type": "application/json",
            "response_json_schema": json_schema,
            "safety_settings": safety_settings_block_none,
        }

        # Patch 통계 추적
        patch_stats = {
            "total": total_patches,
            "success": 0,
            "failed": 0,
            "safety_blocked": 0,
        }

        async def _process_patch_batch(batch_idx, patches_chunk):
            """Process a batch of patches in a single Gemini API call"""
            hotspots_for_batch = []
            
            try:
                # Multi-image Contents 구성: [prompt, "[Image 1]", image1, "[Image 2]", image2, ...]
                contents = [prompt]
                for idx_p, p_data in enumerate(patches_chunk):
                    # 모델이 이미지를 식별할 수 있도록 텍스트 마커 삽입
                    contents.append(f"Image {idx_p + 1}:")
                    image_part = types.Part.from_bytes(data=p_data['image_bytes'], mime_type="image/jpeg")
                    contents.append(image_part)
                    
                async def _call_api(**kwargs):
                    used_model = kwargs.get("model_name", model_name)
                    resp = await client.aio.models.generate_content(
                        model=used_model,
                        contents=contents,
                        config=api_config
                    )
                    return resp
                    
                response = await async_retry_with_backoff(
                    _call_api,
                    max_retries=3,
                    context_name=f"Batch {batch_idx} ({len(patches_chunk)} images)",
                    model_name=model_name
                )
                
                # 응답 처리
                is_safety_blocked = False
                if not hasattr(response, "candidates") or not response.candidates:
                    hotspots_for_batch = []
                else:
                    candidate = response.candidates[0]
                    is_safety_blocked = (
                        hasattr(candidate, "safety_ratings") 
                        and candidate.safety_ratings
                        and any(r.probability in ["HIGH", "MEDIUM"] for r in candidate.safety_ratings)
                    )
                    
                    if is_safety_blocked:
                        logger.warning(f"Batch {batch_idx}: Safety block detected. Skipping {len(patches_chunk)} patches.")
                    else:
                        response_text = getattr(response, "text", None)
                        if response_text:
                            parsed = HotspotDetectionResult.model_validate_json(response_text)
                            hotspots_for_batch = parsed.hotspots
                            
                            # API total_count 로깅
                            api_total = parsed.total_count
                            actual_len = len(hotspots_for_batch)
                            if api_total != actual_len:
                                logger.warning(f"Batch {batch_idx}: API total_count mismatch (returned '{api_total}', parsed '{actual_len}')")
                
                # 통계 (배치 단위가 아닌 패치 개수 기준으로 합산)
                if is_safety_blocked:
                    patch_stats["safety_blocked"] += len(patches_chunk)
                else:
                    patch_stats["success"] += len(patches_chunk)
                    
            except Exception as e:
                logger.warning(f"Batch {batch_idx} Analysis failed: {e}")
                patch_stats["failed"] += len(patches_chunk)
                
            # 전체 배치에서 찾은 핫스팟들을 반환
            # 이제 각 핫스팟에는 'image_index' 속성이 포함되어 있습니다.
            return (patches_chunk, hotspots_for_batch)

        # 3. Task 생성 및 병렬 처리
        tasks = []
        for idx, batch in enumerate(patch_batches):
            tasks.append(_process_patch_batch(idx, batch))
            
        results = await asyncio.gather(*tasks)
        
        # 패치 통계 로깅
        success_rate = (patch_stats["success"] / total_patches * 100) if total_patches > 0 else 0
        logger.info(
            f"Hotspot Detector: Batch Processing stats — "
            f"total patches: {total_patches}, success: {patch_stats['success']}, "
            f"failed: {patch_stats['failed']}, safety_blocked: {patch_stats['safety_blocked']} "
            f"(success rate: {success_rate:.1f}%)"
        )
        
        # 4. Aggregation & Coordinate Mapping
        raw_hotspots = []
        original_size = get_image_size(temp_image_path)
        global_hotspot_id = 1
        
        for patches_chunk, patch_hotspots in results:
            if not patch_hotspots:
                continue
                
            for h in patch_hotspots:
                h_dict = h.model_dump(mode='json')
                
                # 프롬프트 지시대로 모델이 1-based index를 반환한다고 가정
                img_idx = h_dict.get('image_index', 1) - 1
                
                # 인덱스 유효성 검사 (Hallucination 방어)
                if img_idx < 0:
                    img_idx = 0
                elif img_idx >= len(patches_chunk):
                    logger.warning(f"Hotspot Detector: Model hallucinates image_index {img_idx + 1}. Bounding it to Max {len(patches_chunk)}.")
                    img_idx = len(patches_chunk) - 1
                    
                target_patch = patches_chunk[img_idx]
                offset = target_patch['offset']
                p_size = target_patch['size']
                scale_factor = target_patch.get("scale_factor", 1.0)
                
                # Map Coordinates Local -> Global (스케일 팩터 적용)
                global_box = map_box_to_global(
                    h_dict['box_2d'], 
                    offset, 
                    p_size, 
                    original_size,
                    scale_factor=scale_factor
                )
                
                h_dict['box_2d'] = global_box
                h_dict['id'] = global_hotspot_id
                
                raw_hotspots.append(h_dict)
                global_hotspot_id += 1
                
        logger.info(f"Hotspot Detector: {len(raw_hotspots)} raw hotspots detected across all patches.")
        
        # 4. Deduplication (NMS) — config에서 IoU 임계값 참조
        final_hotspots = non_max_suppression(raw_hotspots, iou_threshold=config.HOTSPOT_NMS_IOU_THRESHOLD)
        
        # ID Renumbering + 디버깅 필드 제거
        for idx, h in enumerate(final_hotspots, 1):
            h['id'] = idx
            h.pop('_origin_patch', None)  # 디버깅 필드 제거
            
        final_count = len(final_hotspots)
        logger.info(f"Hotspot Detector: {final_count} unique hotspots remaining after NMS.")
        
        # 5. Result Construction
        if final_count == 0:
            logger.warning("Hotspot Detector: No hotspots detected (NMS 후).")
            result = {
                "hotspots": [],
                "corrected_total_count": 0,
                "analysis_status": "NO_HOTSPOTS_DETECTED",
            }
            _update_image_path_in_result(result, temp_image_path, image_path)
            return result
            
        else:
            # Log final results
            for h in final_hotspots:
                logger.info(f"   - ID {h.get('id')}: Score {h.get('severity_score')}")
        
        # State Update
        result = {
            "hotspots": final_hotspots,
            "corrected_total_count": final_count,
            "analysis_status": "DETECTED",
        }
        _update_image_path_in_result(result, temp_image_path, image_path)
        
        return result

    except Exception as e:
        error_msg = f"Hotspot Detector: Global Error: {e}"
        logger.error(error_msg, exc_info=True)
        # 에러 발생 시에도 analysis_status 설정 + 임시 파일 경로 업데이트
        result = {
            "hotspots": [],
            "errors": [error_msg],
            "analysis_status": "ERROR",
        }
        # temp_image_path가 None인 경우 image_path로 fallback (예외 시 경로 일관성 확보)
        safe_image_path = temp_image_path or image_path
        _update_image_path_in_result(result, safe_image_path, image_path)
        return result
