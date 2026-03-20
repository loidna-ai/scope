"""
사전 처리 노드 (Preprocessor Node)
Hotspot별 Crop + Classification + Enhancement를 메인 그래프에서 1회만 수행합니다.

목적:
  - Contact, Necking, Deform 등 전문가가 동일 이미지에 대해
    Crop/Classification/Enhancement를 각각 수행하는 중복을 제거
  - 전처리 결과를 InvestigationState.preprocessed_hotspots에 저장
  - 각 전문가 Worker는 전처리 결과를 그대로 사용하여 'Analyze' 단계만 수행

설계 원칙:
  - current_hotspot 딕셔너리에 roi_image_path, component_type을 미리 채워 전달
  - Worker는 current_hotspot에 해당 필드가 존재하면 Crop/Classification/Enhancement 건너뜀
  - Enhancement까지 전처리기에서 완료하여 hotspot당 정확히 1회만 실행
  - 전처리 실패 시 원본 hotspot을 그대로 유지 (Graceful Fallback)
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import cv2
import config
from config import TOP_N_HOTSPOTS, MIN_SEVERITY_FOR_ANALYSIS
from src.state import InvestigationState
from src.utils import crop_roi_from_box, async_retry_with_backoff, get_genai_client
from src.utils.logging_config import setup_logger
from src.utils.expert_api_utils import call_classifier_api
from src.utils.expert_image_utils import load_expert_images
from src.models.component_models import ComponentClassification
from src.prompts.common_prompts import get_component_classifier_prompt
from src.nodes.enhancement import ImageEnhancer
from src.nodes.enhancement_cache import get_cached_enhancement, save_enhancement_cache
from google.genai import types

logger = setup_logger(__name__)


# ---------------------------------------------------------------------------
# Private helpers (Crop, Classification, Enhancement)
# ---------------------------------------------------------------------------

_enhancement_lock = asyncio.Lock()

async def _crop_roi(
    hotspot_id: str,
    image_path: str,
    box_2d: Optional[Dict[str, Any]],
) -> str:
    """
    ROI 크롭만 수행 (Enhancement는 각 전문가가 필요할 때만 실행).

    Returns:
        roi_image_path: 크롭된 이미지 경로 (실패 시 원본 image_path)
    """
    roi_image_path = image_path

    if not box_2d:
        return roi_image_path

    logger.debug(f"Preprocessor {hotspot_id}: crop from {box_2d} with padding 0.4")
    try:
        cropped_path = await asyncio.to_thread(crop_roi_from_box, image_path, box_2d, padding_ratio=0.4)
        logger.info(f"Preprocessor {hotspot_id}: Crop done → {cropped_path}")
        roi_image_path = cropped_path
    except Exception as crop_err:
        logger.error(f"Preprocessor {hotspot_id}: Crop failed: {crop_err}")

    return roi_image_path


async def _classify(
    hotspot_id: str,
    roi_image_path: str,
    image_path: str,
    box_2d: Optional[Dict[str, Any]] = None,
) -> str:
    """
    컴포넌트 분류 (공유 전처리용).

    Returns:
        component_type: "Wire" | "Terminal" | "Splice" | "Plug" | "Unknown"
    """
    try:
        logger.info(f"Preprocessor {hotspot_id}: Classifying component...")
        original_image_data, roi_image_data = await load_expert_images(roi_image_path, image_path)

        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        prompt = get_component_classifier_prompt(roi_image_path, box_2d=box_2d)

        parts = [prompt]
        for img_data in [original_image_data, roi_image_data]:
            parts.append(types.Part.from_bytes(data=img_data, mime_type="image/jpeg"))

        async def _call_wrapper(**kwargs):
            return await call_classifier_api(
                client=kwargs["client"],
                model_name=kwargs["model_name"],
                parts=kwargs["parts"],
                response_schema=ComponentClassification,
                context_name=f"Preprocessor #{hotspot_id}",
            )

        response = await async_retry_with_backoff(
            _call_wrapper,
            client=client,
            model_name=model_name,
            parts=parts,
            context_name=f"Preprocessor #{hotspot_id}",
            max_retries=5,
        )

        classification = ComponentClassification.model_validate_json(response.text)
        component_type = classification.deduced_type
        logger.info(
            f"Preprocessor {hotspot_id}: → {component_type} "
            f"(conf: {classification.confidence}%)"
        )
        return component_type

    except Exception as e:
        logger.error(f"Preprocessor {hotspot_id}: Classification failed: {e}", exc_info=True)
        return "Unknown"


async def _enhance_roi(
    hotspot_id: str,
    roi_image_path: str,
) -> str:
    """
    ROI 이미지 Enhancement (캐싱 적용).
    동시성 한계로 인한 OOM 방지를 위해 순차 실행(Lock) 적용.

    Returns:
        enhanced_image_path: Enhancement된 이미지 경로 (실패 시 원본 경로)
    """
    enhanced_path = roi_image_path

    try:
        logger.info(f"Preprocessor {hotspot_id}: Waiting for enhancement lock...")
        async with _enhancement_lock:
            logger.info(f"Preprocessor {hotspot_id}: Applying {config.SR_SCALE}x enhancement...")

            # 캐시 확인
            cached_path = await asyncio.to_thread(get_cached_enhancement, roi_image_path)
            if cached_path:
                logger.info(f"Preprocessor {hotspot_id}: Cache hit → {cached_path}")
                # 캐시된 파일을 원본 경로 위에 덮어쓰기 (Worker가 roi_image_path만 참조)
                import shutil
                shutil.copy2(cached_path, roi_image_path)
                return roi_image_path

            # 이미지 로드
            img = await asyncio.to_thread(cv2.imread, roi_image_path)
            if img is None:
                logger.warning(f"Preprocessor {hotspot_id}: Cannot read image for enhancement")
                return roi_image_path

            # Enhancement 수행
            def _do_enhance(img_data, path):
                enhancer = ImageEnhancer()
                enhanced_img = enhancer.upscale(img_data)
                cv2.imwrite(path, enhanced_img)
                return path

            enhanced_path = await asyncio.to_thread(_do_enhance, img, roi_image_path)

            # 캐시 저장
            await asyncio.to_thread(save_enhancement_cache, roi_image_path, enhanced_path)
            logger.info(f"Preprocessor {hotspot_id}: Enhancement done → {enhanced_path}")

    except Exception as enh_err:
        logger.warning(f"Preprocessor {hotspot_id}: Enhancement failed: {enh_err}")

    return enhanced_path


# ---------------------------------------------------------------------------
# Public Node
# ---------------------------------------------------------------------------

async def preprocess_hotspots_node(state: InvestigationState) -> Dict[str, Any]:
    """
    [메인 그래프 노드] Hotspot별 Crop + Classification + Enhancement를 1회만 수행.

    hotspot_detector → preprocess_hotspots_node → [contact, deform, necking, ...]

    결과:
        preprocessed_hotspots: List[Dict]
            각 항목의 구조:
            {
                ...original hotspot fields...,
                "roi_image_path": str,       # 크롭+Enhancement 완료된 이미지 경로
                "component_type": str,       # "Wire" | "Terminal" | ...
                "_preprocessed": True        # Worker 측 건너뜀 플래그
            }
    """
    # ── 빠른 탈출 경로 ──────────────────────────────────────────────────────
    analysis_status = state.get("analysis_status")
    if analysis_status in ("NO_HOTSPOTS_DETECTED", "ERROR"):
        logger.info(f"Preprocessor: Skipping (analysis_status={analysis_status})")
        return {"preprocessed_hotspots": []}

    hotspots: List[Dict[str, Any]] = state.get("hotspots") or []
    image_path: str = state.get("image_path", "")

    if not hotspots or not image_path:
        logger.warning("Preprocessor: hotspots or image_path missing — skipping")
        return {"preprocessed_hotspots": []}

    # ── Top-N 선택 (전문가 그래프와 동일한 기준) ────────────────────────────
    valid = [h for h in hotspots if h.get("severity_score", 0) >= MIN_SEVERITY_FOR_ANALYSIS]
    selected: List[Dict[str, Any]] = sorted(
        valid, key=lambda x: x.get("severity_score", 0), reverse=True
    )[:TOP_N_HOTSPOTS]

    if not selected:
        logger.info("Preprocessor: No valid hotspots after filtering")
        return {"preprocessed_hotspots": []}

    logger.info(f"Preprocessor: Processing {len(selected)} hotspot(s) …")

    # ── 각 Hotspot 전처리 (Crop → Classification → Enhancement) ──────
    async def _process_one(hotspot: Dict[str, Any]) -> Dict[str, Any]:
        hid = hotspot.get("id", "unknown")
        boxes = hotspot.get("boxes", {})
        source_images = hotspot.get("source_images", [])
        
        # 하위 호환성 폴백
        if not source_images:
            if "image_path" in state and "box_2d" in hotspot:
                source_images = [state["image_path"]]
                boxes = {state["image_path"]: hotspot["box_2d"]}
            else:
                source_images = [image_path]
                boxes = {image_path: hotspot.get("box_2d")}
                
        roi_image_paths = {}
        for img_path in source_images:
            box = boxes.get(img_path)
            if box:
                roi_p = await _crop_roi(hid, img_path, box)
                enh_p = await _enhance_roi(hid, roi_p)
                roi_image_paths[img_path] = enh_p
                
        # Classification (대표 이미지 1개로 추론, 성능 최적화)
        primary_img = source_images[0] if source_images else image_path
        primary_roi = roi_image_paths.get(primary_img, primary_img)
        primary_box = boxes.get(primary_img)
        
        component_type = await _classify(hid, primary_roi, primary_img, box_2d=primary_box)

        enriched = dict(hotspot)
        enriched["roi_image_paths"] = roi_image_paths
        enriched["roi_image_path"] = primary_roi  # 호환성 유지용 (가장 대표 값)
        enriched["component_type"] = component_type
        enriched["_preprocessed"] = True
        
        # 단계별 성공 플래그
        enriched["_crop_done"] = any(p != img for img, p in roi_image_paths.items())
        enriched["_classify_done"] = (component_type != "Unknown")
        enriched["_enhance_done"] = enriched["_crop_done"]
        return enriched

    # 병렬 전처리 (asyncio.gather)
    preprocessed: List[Dict[str, Any]] = await asyncio.gather(
        *[_process_one(h) for h in selected]
    )

    logger.info(f"Preprocessor: Done - {len(preprocessed)} hotspot(s) ready")
    return {"preprocessed_hotspots": list(preprocessed)}
