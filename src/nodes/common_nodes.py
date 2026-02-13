"""
공통 노드 정의
모든 전문가가 공통으로 사용하는 노드들

- hotspot_detector_node: [Overlap Grid] 이미지 패치 분할 → Gemini 병렬 분석 → NMS 중복 제거
- _update_image_path_in_result: 결과에 image_path 업데이트 헬퍼
"""
import asyncio
import os
import threading
from pathlib import Path
from typing import Any, Dict

from google import genai
from google.genai import types

from src.models.hotspot_models import HotspotDetectionResult
from src.prompts.common_prompts import get_micro_evidence_prompt
from src.state import InvestigationState
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file
from src.utils import async_retry_with_backoff
from src.utils.image_processing import get_image_size, map_box_to_global, slice_image
from src.utils.logging_config import setup_logger
from src.utils.nms import non_max_suppression

logger = setup_logger("common_nodes")

# === Global Rate Limiter for Hotspot Detector ===
from aiolimiter import AsyncLimiter
import config

_hotspot_rate_limiter = AsyncLimiter(
    max_rate=config.GEMINI_TIER1_RPM,
    time_period=60
)
_hotspot_semaphore = asyncio.Semaphore(config.GEMINI_TIER1_CONCURRENT)


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


def hotspot_detector_node(state: InvestigationState) -> Dict[str, Any]:
    """
    [Overlap Grid Strategy] Hotspot Detector Node
    
    1. 슬라이싱: 이미지를 고해상도 패치로 분할 (Overlap 적용)
    2. 병렬 처리: 각 패치를 독립적으로 Gemini API에 전송 (Async)
    3. 종합: 결과를 수집하고 좌표를 전역 공간으로 매핑
    4. 중복 제거: NMS 알고리즘으로 겹치는 Hotspot 병합
    
    Note: LangGraph compatibility - sync wrapper with async internal logic
    """
    async def _async_detector_logic():
        """Async implementation of hotspot detection with Overlap Grid"""
        # [환경 변수 검증] API Key 존재 여부 확인
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            error_msg = "Hotspot Detector: 환경 변수 GEMINI_API_KEY가 설정되지 않았습니다."
            logger.error(error_msg)
            return {"hotspots": [], "errors": [error_msg]}
        
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
            # 1. Image Slicing
            # [Config] Patch Size: 1024, Overlap: 200 (검토된 최적값)
            logger.info(f"Hotspot Detector: Slicing image {temp_image_path}...")
            patches = await asyncio.to_thread(slice_image, temp_image_path, patch_size=1024, overlap=200)
            
            if not patches:
                raise ValueError("Image slicing failed (no patches generated).")
                
            logger.info(f"Hotspot Detector: Generated {len(patches)} patches. Starting parallel analysis...")

            # 2. Parallel API Execution
            client = genai.Client(api_key=api_key)
            model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview") # Flash 권장
            prompt = get_micro_evidence_prompt()
            
            # Safety settings: BLOCK_NONE
            safety_settings_block_none = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ]
            
            # Schema setup
            json_schema = HotspotDetectionResult.model_json_schema()
            req = json_schema.setdefault("required", [])
            if "hotspots" not in req:
                req.append("hotspots")
            
            api_config = {
                "response_mime_type": "application/json",
                "response_json_schema": json_schema,
                "safety_settings": safety_settings_block_none,
                # Flash 모델은 thinking_config 지원 여부를 확인해야 함. 일단 제외.
            }

            async def _process_patch(patch_data):
                """Process a single patch with rate limiting"""
                patch_idx = patch_data['index']
                
                # === Apply Rate Limiting ===
                async with _hotspot_rate_limiter:  # RPM control (20/min)
                    async with _hotspot_semaphore:  # Concurrent control (5)
                        try:
                            # Part 생성 시 mime_type="image/jpeg"로 고정 (slice_image가 JPEG bytes 반환)
                            image_part = types.Part.from_bytes(
                                data=patch_data['image_bytes'],
                                mime_type="image/jpeg"
                            )
                            
                            # Retry logic for individual patch
                            async def _call_api(**kwargs):
                                # model_name in kwargs: Smart Fallback 지원 (503 시 async_retry_with_backoff가 전환)
                                used_model = kwargs.get("model_name", model_name)
                                # Note: Using async generate_content if available, otherwise wrap synchronous
                                # genai.Client usually synchronous unless async_client used.
                                # Here we wrap synchronous call in thread for true parallelism
                                resp = await asyncio.to_thread(
                                    client.models.generate_content,
                                    model=used_model,
                                    contents=[prompt, image_part],
                                    config=api_config
                                )
                                return resp

                            response = await async_retry_with_backoff(
                                _call_api, 
                                max_retries=3,  # 패치 단위는 재시도 횟수 줄임
                                context_name=f"Patch {patch_idx}",
                                model_name=model_name  # Smart Fallback 지원
                            )
                            
                            # Validation & Parsing
                            if not hasattr(response, "candidates") or not response.candidates:
                                return []
                            
                            # Safety Block Check (skip if blocked)
                            candidate = response.candidates[0]
                            # Safety ratings check
                            if hasattr(candidate, "safety_ratings") and candidate.safety_ratings:
                                if any(r.probability in ["HIGH", "MEDIUM"] for r in candidate.safety_ratings):
                                    logger.warning(f"Patch {patch_idx}: Safety block detected. Skipping.")
                                    return []

                            response_text = getattr(response, "text", None)
                            if not response_text:
                                return []
                            
                            result = HotspotDetectionResult.model_validate_json(response_text)
                            return result.hotspots
                            
                        except Exception as e:
                            logger.warning(f"Patch {patch_idx}: Analysis failed: {e}")
                            return []

            # Run all patches in parallel
            tasks = [_process_patch(p) for p in patches]
            patch_results_list = await asyncio.gather(*tasks)
            
            # 3. Aggregation & Coordinate Mapping
            raw_hotspots = []
            original_size = get_image_size(temp_image_path)
            
            global_hotspot_id = 1
            
            for i, patch_hotspots in enumerate(patch_results_list):
                patch_info = patches[i]
                offset = patch_info['offset']
                p_size = patch_info['size']
                
                if not patch_hotspots:
                    continue
                    
                for h in patch_hotspots:
                    # Convert Pydantic to Dict
                    h_dict = h.model_dump(mode='json')
                    
                    # Map Coordinates Local -> Global
                    global_box = map_box_to_global(
                        h_dict['box_2d'], 
                        offset, 
                        p_size, 
                        original_size
                    )
                    
                    # Update Info
                    h_dict['box_2d'] = global_box
                    h_dict['id'] = global_hotspot_id # 임시 ID (나중에 재정렬)
                    h_dict['_origin_patch'] = patch_info['index'] # 디버깅용
                    
                    raw_hotspots.append(h_dict)
                    global_hotspot_id += 1
                    
            logger.info(f"Hotspot Detector: {len(raw_hotspots)} raw hotspots detected across all patches.")
            
            # 4. Deduplication (NMS)
            # [Config] IoU Threshold: 0.3 (겹치는 영역이 30% 이상이면 중복으로 간주하고 높은 점수 유지)
            final_hotspots = non_max_suppression(raw_hotspots, iou_threshold=0.3)
            
            # ID Renumbering
            for idx, h in enumerate(final_hotspots, 1):
                h['id'] = idx
                
            final_count = len(final_hotspots)
            logger.info(f"Hotspot Detector: {final_count} unique hotspots remaining after NMS.")
            
            # 5. Result Construction
            if final_count == 0:
                logger.warning("Hotspot Detector: No hotspots detected (NMS 후).")
                result = {
                    "hotspots": [],
                    "corrected_total_count": 0,
                    "analysis_status": "NO_HOTSPOTS_DETECTED"
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
                "analysis_status": "DETECTED"
            }
            _update_image_path_in_result(result, temp_image_path, image_path)
            
            return result

        except Exception as e:
            error_msg = f"Hotspot Detector: Global Error: {e}"
            logger.error(error_msg, exc_info=True)
            # 에러 발생 시에도 임시 파일을 생성한 경우 image_path 업데이트
            result = {"hotspots": [], "errors": [error_msg]}
            _update_image_path_in_result(result, temp_image_path, image_path)
            return result
        # Note: 임시 파일 정리는 하지 않음. image_path가 State에 저장되어 후속 노드에서 사용됨.
        # 파일 정리는 전체 파이프라인 완료 후 main.py나 호출 측에서 처리해야 함.
    
    # Execute async logic with proper event loop handling
    # This prevents "RuntimeError: This event loop is already running" in nested async contexts
    try:
        # Try to get the current event loop
        loop = asyncio.get_event_loop()
        
        # Check if we're already in a running event loop
        if loop.is_running():
            # We're inside an async context (e.g., LangGraph's astream)
            # Use asyncio.ensure_future and wait for completion synchronously
            # Note: This is a workaround for sync-in-async compatibility
            result_container = {}
            exception_container = {}
            
            def run_in_new_loop():
                """Run the async function in a new event loop in a separate thread"""
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result = new_loop.run_until_complete(_async_detector_logic())
                    result_container['value'] = result
                except Exception as e:
                    exception_container['error'] = e
                finally:
                    new_loop.close()
            
            # Run in a separate thread to avoid event loop conflicts
            thread = threading.Thread(target=run_in_new_loop)
            thread.start()
            thread.join()
            
            if 'error' in exception_container:
                raise exception_container['error']
            return result_container.get('value', {"hotspots": [], "errors": ["Unknown execution error"]})
        else:
            # No running loop - safe to use asyncio.run()
            return asyncio.run(_async_detector_logic())
            
    except RuntimeError:
        # No event loop exists - create one with asyncio.run()
        return asyncio.run(_async_detector_logic())


