"""
Identity Fusion (다중 뷰 객체 병합) 로직
여러 각도/위치에서 탐지된 Hotspot들을 하나의 객체로 병합
"""
import json
import os
from typing import Any, Dict, List, Optional

from google.genai import types

import config
from src.models.hotspot_models import IdentityFusionResult
from src.prompts.common_prompts import get_identity_fusion_prompt
from src.tools.experts.expert_utils import load_image_data
from src.utils import async_retry_with_backoff
from src.utils.logging_config import setup_logger

logger = setup_logger("identity_fusion")

async def run_identity_fusion(
    client: Any,
    image_paths: List[str],
    final_raw_hotspots: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    다중 이미지에서 탐지된 Hotspot들을 분석하여 동일 객체여부를 판단하고 병합합니다.
    """
    if len(image_paths) <= 1:
        # 단일 이미지인 경우 Fusion 없이 1:1 매핑
        return _fallback_to_mapping(final_raw_hotspots)

    logger.info(f"Identity Fusion: Running for {len(final_raw_hotspots)} hotspots across {len(image_paths)} images...")
    
    fusion_prompt = get_identity_fusion_prompt()
    # 프롬프트에 식별하기 쉽도록 Raw Hotspot 데이터를 주입
    fusion_prompt += "\n\n<raw_hotspots_json>\n" + json.dumps(final_raw_hotspots, ensure_ascii=False, indent=2) + "\n</raw_hotspots_json>"
    
    # 원본 이미지 바이트 데이터 로드
    fusion_image_bytes = []
    for path in image_paths:
        try:
            b = load_image_data(path)
            fusion_image_bytes.append(b)
        except Exception as e:
            logger.error(f"Failed to load image for Identity Fusion: {path} - {e}")
    
    if not fusion_image_bytes:
        logger.warning("Identity Fusion: No image bytes loaded. Falling back to 1:1 mapping.")
        return _fallback_to_mapping(final_raw_hotspots)

    # Fusion 모델 설정
    fusion_model = getattr(config, 'GEMINI_PRO_MODEL_NAME', config.GEMINI_MODEL_NAME)
    
    json_schema_fusion = IdentityFusionResult.model_json_schema()
    req_f = json_schema_fusion.setdefault("required", [])
    if "unified_hotspots" not in req_f: req_f.append("unified_hotspots")
    if "reasoning" not in req_f: req_f.append("reasoning")
    
    contents = [fusion_prompt]
    for idx, b in enumerate(fusion_image_bytes):
        contents.append(f"Image {idx + 1}:")
        contents.append(types.Part.from_bytes(data=b, mime_type="image/jpeg"))
        
    f_api_config = {
        "response_mime_type": "application/json",
        "response_json_schema": json_schema_fusion,
    }
    
    async def _call_fusion():
        return await client.aio.models.generate_content(
            model=fusion_model,
            contents=contents,
            config=f_api_config
        )
        
    try:
        f_response = await async_retry_with_backoff(
            _call_fusion, 
            max_retries=3, 
            context_name="Identity Fusion", 
            model_name=fusion_model
        )
        
        if hasattr(f_response, "text") and f_response.text:
            f_parsed = IdentityFusionResult.model_validate_json(f_response.text)
            unified_hotspots = [u.model_dump(mode='json') for u in f_parsed.unified_hotspots]
            logger.info(f"Identity Fusion: Complete. Merged into {len(unified_hotspots)} Unified Hotspots.")
            logger.info(f"Identity Fusion: Reasoning: {f_parsed.reasoning}")
            return unified_hotspots
        else:
            raise ValueError("Empty response from Identity Fusion")
    except Exception as e:
        logger.error(f"Identity Fusion failed: {e}. Falling back to 1:1 mapping.")
        return _fallback_to_mapping(final_raw_hotspots)

def _fallback_to_mapping(final_raw_hotspots: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fusion 실패 또는 미대상 시 1:1 매핑을 수행합니다."""
    unified_hotspots = []
    for h in final_raw_hotspots:
        h_id = h['id']
        src_path = h['source_image_path']
        uh = {
            "id": h_id,
            "source_images": [src_path],
            "boxes": {src_path: h['box_2d']},
            "severity_score": h.get('severity_score', 0),
            "location_description": h.get('location_description', ''),
            "visual_evidence": h.get('visual_evidence', ''),
            "raw_hotspot_ids": [h_id],
            "roi_image_paths": {},
            "component_type": None,
            "_preprocessed": False
        }
        unified_hotspots.append(uh)
    return unified_hotspots
