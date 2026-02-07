"""
공통 노드 정의
모든 전문가가 공통으로 사용하는 노드들
"""
from typing import Dict, Any
import json
import tempfile
import os
from pathlib import Path
from src.state import InvestigationState
from src.utils import retry_with_backoff
from src.tools.experts.expert_utils import (
    extract_image_from_payload,
    save_bytes_to_temp_file,
    _load_image_data
)
from src.utils.logging_config import setup_logger
from src.prompts.common_prompts import get_multi_hotspot_prompt


logger = setup_logger("common_nodes")


def _update_image_path_in_result(
    result: Dict[str, Any],
    temp_image_path: str,
    existing_image_path: str = None
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


def _detect_mime_type(image_path: str) -> str:
    """
    이미지 파일의 MIME 타입을 동적으로 감지
    파일 시그니처(매직 넘버) 우선, 확장자는 보조 수단
    
    Args:
        image_path: 이미지 파일 경로
    
    Returns:
        MIME 타입 문자열 (예: "image/jpeg", "image/png", "image/webp", "image/gif", "image/heic", "image/bmp")
    """
    # 파일 시그니처 기반 감지 (매직 넘버)
    try:
        with open(image_path, 'rb') as f:
            header = f.read(12)
        
        # JPEG: FF D8 (JPEG 파일 시그니처 - 2바이트)
        if header[:2] == b'\xff\xd8':
            return "image/jpeg"
        # PNG: 89 50 4E 47 0D 0A 1A 0A (PNG 파일 시그니처)
        elif header[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        # WebP: RIFF ... WEBP (WebP 파일 시그니처)
        elif header[:4] == b'RIFF' and len(header) >= 12 and header[8:12] == b'WEBP':
            return "image/webp"
        # GIF: 47 49 46 38 (GIF 파일 시그니처 - "GIF8")
        elif header[:4] in (b'GIF87a', b'GIF89a'):
            return "image/gif"
        # HEIC/HEIF: ftyp 박스 확인 (offset 4~8)
        elif len(header) >= 12 and header[4:8] == b'ftyp':
            # HEIC: ftyp 뒤에 heic, heix, hevc, hevx 등
            if header[8:12] in (b'heic', b'heix', b'hevc', b'hevx', b'mif1'):
                return "image/heic"
            # AVIF: ftyp 뒤에 avif
            elif header[8:12] == b'avif':
                return "image/avif"
            # else: ftyp이지만 이미지가 아닌 형식 (MP4 등) - fallthrough
        # BMP: 42 4D (BMP 파일 시그니처 - "BM")
        elif header[:2] == b'BM':
            return "image/bmp"
    except Exception as e:
        logger.warning(f"MIME 타입 시그니처 감지 실패: {e}, 확장자 기반으로 폴백")
    
    # 확장자 기반 폴백
    ext = Path(image_path).suffix.lower()
    if ext in ['.png']:
        detected_type = "image/png"
    elif ext in ['.jpg', '.jpeg']:
        detected_type = "image/jpeg"
    elif ext == '.webp':
        detected_type = "image/webp"
        logger.info("WebP 형식 감지: Gemini API 지원 여부 확인 필요")
    elif ext == '.gif':
        detected_type = "image/gif"
    elif ext in ['.heic', '.heif']:
        detected_type = "image/heic"
        logger.warning("HEIC/HEIF 형식 감지: Gemini API 지원 여부에 따라 오류 발생 가능")
    elif ext == '.bmp':
        detected_type = "image/bmp"
    elif ext == '.avif':
        detected_type = "image/avif"
        logger.info("AVIF 형식 감지: Gemini API 지원 여부 확인 필요")
    else:
        detected_type = "image/jpeg"
        logger.warning(f"알 수 없는 이미지 형식: {ext}, 기본값 image/jpeg 사용")
    
    # 시그니처 감지 실패 시 확장자 기반 결과 반환
    logger.debug(f"MIME 타입 감지 (확장자 기반): {detected_type}")
    return detected_type

def hotspot_detector_node(state: InvestigationState) -> Dict[str, Any]:
    """
    공통 Hotspot Detector 노드
    InvestigationState를 사용하여 전체 이미지에서 다중 발화 지점(Hotspots) 탐색
    
    Args:
        state: InvestigationState (payload 포함)
        
    Returns:
        {"hotspots": List[Dict]} - 탐지된 Hotspot 리스트
    """
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
        logger.info(f"Hotspot Detector: Starting analysis (Image: {temp_image_path})")
        
        # 이미지 데이터 로드
        image_data_bytes = _load_image_data(temp_image_path)
        
        # 프롬프트 생성
        prompt = get_multi_hotspot_prompt()
        
        # 🔥 Pydantic Structured Output (Gemini Official Best Practice)
        from src.models.hotspot_models import HotspotDetectionResult
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=api_key)
        
        # 이미지 MIME 타입 동적 감지
        mime_type = _detect_mime_type(temp_image_path)
        logger.debug(f"Hotspot Detector: Detected MIME type: {mime_type}")
        
        # 이미지 파트 구성 (고해상도 설정)
        image_part = types.Part.from_bytes(
            data=image_data_bytes,
            mime_type=mime_type
        )
        
        # Safety settings: 모든 카테고리를 BLOCK_NONE으로 설정
        # Note: Gemini API는 일부 카테고리(특히 HARM_CATEGORY_DANGEROUS_CONTENT)에서
        # BLOCK_NONE 설정을 무시하고 여전히 block할 수 있음 (API 정책 제한)
        safety_settings_block_none = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # 공통 재시도 로직 (src.utils.retry_with_backoff): 빈 응답, EOF/json_invalid(잘림) 재시도
        model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
        json_schema = HotspotDetectionResult.model_json_schema()
        # hotspots가 optional이면 Gemini가 생략할 수 있음 -> required로 명시
        req = json_schema.setdefault("required", [])
        if "hotspots" not in req:
            req.append("hotspots")
        api_config = {
            "response_mime_type": "application/json",
            "response_json_schema": json_schema,
            "max_output_tokens": 16384,
            "media_resolution": "MEDIA_RESOLUTION_HIGH",
            "safety_settings": safety_settings_block_none,
            "thinking_config": {"include_thoughts": True, "thinking_level": "HIGH"},
        }

        def _call_hotspot_api():
            response = client.models.generate_content(
                model=model_name, contents=[prompt, image_part], config=api_config
            )
            
            # API 응답 검증 강화
            if not hasattr(response, "candidates") or not response.candidates:
                raise ValueError("Gemini API 응답에 candidates가 없습니다.")
            
            candidate = response.candidates[0]
            finish_reason = getattr(candidate, "finish_reason", "Unknown")
            # Safety block 체크 (safety_ratings가 None일 수 있음 - Gemini API 응답 차이)
            if hasattr(candidate, "safety_ratings") and candidate.safety_ratings is not None:
                blocked = any(
                    rating.probability in ["HIGH", "MEDIUM"] 
                    for rating in candidate.safety_ratings
                )
                if blocked:
                    # [Design Decision] Safety block은 재시도해도 동일한 결과이므로
                    # ValueError를 발생시켜 retry_with_backoff가 재시도하지 않도록 함
                    logger.error(f"Hotspot Detector: Safety block detected. Finish reason: {finish_reason}")
                    raise ValueError(
                        f"Gemini API safety block detected. Content may violate safety policies. "
                        f"Finish Reason: {finish_reason}"
                    )
            
            response_text = getattr(response, "text", None)
            if not response_text:
                raise ValueError(
                    f"Gemini API 응답이 비어있습니다. "
                    f"(Finish Reason: {finish_reason}, "
                    f"Safety Block: {hasattr(candidate, 'safety_ratings') and candidate.safety_ratings is not None and any(r.probability in ['HIGH', 'MEDIUM'] for r in candidate.safety_ratings)}"
                )
            # [DEBUG] raw 응답 구조 로깅: total_count vs hotspots 실제 개수
            try:
                raw_data = json.loads(response_text)
                raw_total = raw_data.get("total_count")
                raw_hotspots = raw_data.get("hotspots")
                raw_len = len(raw_hotspots) if isinstance(raw_hotspots, list) else "N/A"
                raw_type = type(raw_hotspots).__name__ if raw_hotspots is not None else "None"
                raw_keys = list(raw_data.keys()) if isinstance(raw_data, dict) else "N/A"
                logger.info(
                    f"Hotspot raw response: total_count={raw_total}, "
                    f"len(hotspots)={raw_len}, hotspots_type={raw_type}, raw_keys={raw_keys}"
                )
                if not isinstance(raw_hotspots, list):
                    logger.warning(
                        f"Hotspot raw: hotspots가 리스트가 아님 (type={raw_type}). "
                        f"Pydantic이 default_factory=list로 빈 리스트로 대체함."
                    )
                elif raw_len == 0 and (raw_total or 0) > 0:
                    logger.warning("Hotspot raw: LLM이 total_count>0이지만 hotspots=[]로 반환함 (불일치)")
                elif raw_len > 0:
                    h0 = raw_hotspots[0]
                    logger.debug(f"Hotspot raw first item keys: {list(h0.keys()) if isinstance(h0, dict) else type(h0)}")
            except json.JSONDecodeError as je:
                logger.warning(f"Hotspot raw response: JSON 파싱 실패 - {je}")
            return HotspotDetectionResult.model_validate_json(response_text)

        try:
            detection_result = retry_with_backoff(
                _call_hotspot_api, max_retries=5, context_name="Hotspot Detector"
            )
        except Exception as e:
            logger.error(f"Hotspot Detector: {e}")
            return {"hotspots": [], "errors": [f"Hotspot Detector: 데이터 파싱 오류: {str(e)}"]}

        hotspots = [h.model_dump(mode='json') for h in detection_result.hotspots]
        
        # total_count 검증 및 자동 보정
        actual_count = len(hotspots)
        reported_count = detection_result.total_count
        if actual_count != reported_count:
            logger.warning(
                f"Hotspot Detector: total_count 불일치 감지. "
                f"보고된 개수: {reported_count}, 실제 개수: {actual_count}. "
                f"실제 개수({actual_count})로 자동 보정합니다."
            )
        
        # Note: hotspots는 리스트 컴프리헨션 결과이므로 항상 리스트입니다 (None이 될 수 없음)
        if actual_count == 0:
            logger.warning("Hotspot Detector: No hotspots detected (빈 리스트). 이미지에 분석 가능한 이상 징후가 없거나, 이미지 품질이 낮을 수 있습니다.")
            # 빈 hotspots의 경우 명시적 상태 반환
            result = {
                "hotspots": [],
                "corrected_total_count": 0,
                "analysis_status": "NO_HOTSPOTS_DETECTED"
            }
            _update_image_path_in_result(result, temp_image_path, image_path)
            return result
        else:
            logger.info(f"Hotspot Detector: Found {actual_count} hotspots")
            for h in hotspots:
                logger.info(f"   - ID {h.get('id')}: {h.get('damage_type')} (Score: {h.get('severity_score')})")
        
        # State 업데이트: 임시 파일을 생성한 경우 image_path 추가
        result = {
            "hotspots": hotspots,
            "corrected_total_count": actual_count  # 보정된 total_count
        }
        _update_image_path_in_result(result, temp_image_path, image_path)
        
        return result
        
    except Exception as e:
        error_msg = f"Hotspot Detector: Unexpected Error: {e}"
        logger.error(error_msg, exc_info=True)
        # 에러 발생 시에도 임시 파일을 생성한 경우 image_path 업데이트
        result = {"hotspots": [], "errors": [error_msg]}
        _update_image_path_in_result(result, temp_image_path, image_path)
        return result
    # Note: 임시 파일 정리는 하지 않음. image_path가 State에 저장되어 후속 노드에서 사용됨.
    # 파일 정리는 전체 파이프라인 완료 후 main.py나 호출 측에서 처리해야 함.


