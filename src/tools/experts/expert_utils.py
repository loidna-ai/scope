"""
전문가 공통 유틸리티 함수 (Stateless & Pure)
다중 에이전트 환경에서 동시 호출 시 Race Condition을 방지하기 위해 
모든 전역 상태(Global Client, Cache 등)를 제거하고 매개변수 기반으로 작동하도록 재작성되었습니다.
"""
import os
import json
import base64
import time
import random
import traceback
import tempfile
from typing import Dict, Any, Optional, List, Union, Tuple, Sequence
from pathlib import Path
from google.genai import types, Client

from src.utils.expert_config import get_thinking_config

# MediaResolution enum fallback logic (Stateless helper)
def _get_media_resolution_enum() -> Any:
    """MediaResolution enum을 안전하게 반환합니다."""
    try:
        return types.MediaResolution
    except AttributeError:
        # Fallback if enum is not available in current SDK version
        class MediaResolutionFallback:
            MEDIA_RESOLUTION_UNSPECIFIED = "MEDIA_RESOLUTION_UNSPECIFIED"
            MEDIA_RESOLUTION_LOW = "MEDIA_RESOLUTION_LOW"
            MEDIA_RESOLUTION_MEDIUM = "MEDIA_RESOLUTION_MEDIUM"
            MEDIA_RESOLUTION_HIGH = "MEDIA_RESOLUTION_HIGH"
            MEDIA_RESOLUTION_ULTRA_HIGH = "MEDIA_RESOLUTION_HIGH"  # Fallback to HIGH
        return MediaResolutionFallback


def create_image_part(image_path: str) -> Optional[bytes]:
    """
    이미지 경로를 바이트 데이터로 변환 (Stateless)
    
    Args:
        image_path: 이미지 파일 경로
        
    Returns:
        이미지 바이트 데이터 또는 None
    """
    if not image_path or not os.path.exists(image_path):
        return None
        
    try:
        with open(image_path, "rb") as image_file:
            return image_file.read()
    except Exception as e:
        # 로그는 남기되 상태 변이는 없음
        return None


def save_bytes_to_temp_file(image_data: bytes, suffix: str = '.jpg') -> str:
    """
    이미지 bytes 데이터를 임시 파일로 저장하고 경로 반환 (Stateless I/O)
    
    Args:
        image_data: 이미지 bytes 데이터
        suffix: 기본 파일 확장자
        
    Returns:
        임시 파일 경로
    """
    # 이미지 형식 자동 감지 (Immutable approach: read bytes but don't change them)
    if len(image_data) >= 4 and image_data[:4] == b'\x89PNG':
        actual_suffix = '.png'
    elif len(image_data) >= 3 and image_data[:3] == b'\xff\xd8\xff':
        actual_suffix = '.jpg'
    else:
        actual_suffix = suffix
    
    with tempfile.NamedTemporaryFile(suffix=actual_suffix, delete=False) as temp_file:
        temp_file.write(image_data)
        return temp_file.name


def extract_image_from_payload(payload: Sequence[Any]) -> Optional[bytes]:
    """
    payload에서 첫 번째 이미지 데이터 추출 (Pure)
    """
    if not payload:
        return None
    
    for part in payload:
        if isinstance(part, dict) and "inline_data" in part:
            inline_data = part["inline_data"]
            try:
                return base64.b64decode(inline_data["data"])
            except (KeyError, ValueError, TypeError):
                continue
    return None


def extract_images_from_payload(payload: Sequence[Any]) -> List[bytes]:
    """
    payload에서 모든 이미지 데이터 추출 (Pure)
    """
    if not payload:
        return []
    
    image_data_list = []
    for part in payload:
        if isinstance(part, dict) and "inline_data" in part:
            inline_data = part["inline_data"]
            try:
                image_data_list.append(base64.b64decode(inline_data["data"]))
            except (KeyError, ValueError, TypeError):
                continue
    return image_data_list


def call_gemini_vision(
    client: Client,
    model_name: str,
    prompt: str, 
    image_data: Union[Sequence[bytes], bytes], 
    step_name: str = "Vision",
    verbose: bool = False,
    temperature: float = 0.3,
    thinking_level: str = "medium",
    media_resolution: Optional[Union[str, Any]] = None,
    safety_settings: Optional[List[Dict[str, str]]] = None,
    top_p: Optional[float] = None,
    max_output_tokens: Optional[int] = None,
    response_mime_type: Optional[str] = "application/json"
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Gemini Vision API 호출 및 에러 핸들링 (Stateless & Pure)
    
    Args:
        client: 사용할 GenAI Client 인스턴스 (필수)
        model_name: 사용할 모델 명칭 (필수)
        prompt: 분석 프롬프트
        image_data: 이미지 바이트 (단일 또는 리스트)
        ... 기타 파라미터 ...
        
    Returns:
        tuple: (response_text, thinking_info)
    """
    if client is None:
        return "Error: Client is required for call_gemini_vision", None

    MAX_RETRIES = 3
    
    # image_data 정규화 (Sequence[bytes])
    images = [image_data] if isinstance(image_data, bytes) else image_data
    
    contents = [prompt]
    for img_bytes in images:
        if not img_bytes:
            continue
        mime_type = "image/png"
        if len(img_bytes) >= 3 and img_bytes[:3] == b'\xff\xd8\xff':
            mime_type = "image/jpeg"
        
        contents.append({
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(img_bytes).decode('utf-8')
            }
        })
    
    # Config 구성 (Stateless)
    config_params: Dict[str, Any] = {"temperature": temperature}
    
    thinking_cfg = get_thinking_config(model_name, thinking_level)
    if thinking_cfg:
        config_params["thinking_config"] = thinking_cfg
    
    if top_p is not None: config_params["top_p"] = top_p
    if max_output_tokens is not None: config_params["max_output_tokens"] = max_output_tokens
    if response_mime_type is not None: config_params["response_mime_type"] = response_mime_type
    
    MediaRes = _get_media_resolution_enum()
    if media_resolution:
        if isinstance(media_resolution, str):
            res_map = {
                "high": MediaRes.MEDIA_RESOLUTION_HIGH,
                "MEDIA_RESOLUTION_LOW": MediaRes.MEDIA_RESOLUTION_LOW,
                "MEDIA_RESOLUTION_MEDIUM": MediaRes.MEDIA_RESOLUTION_MEDIUM,
                "MEDIA_RESOLUTION_HIGH": MediaRes.MEDIA_RESOLUTION_HIGH,
                "MEDIA_RESOLUTION_ULTRA_HIGH": getattr(MediaRes, 'MEDIA_RESOLUTION_ULTRA_HIGH', MediaRes.MEDIA_RESOLUTION_HIGH),
            }
            config_params["media_resolution"] = res_map.get(media_resolution, MediaRes.MEDIA_RESOLUTION_HIGH)
        else:
            config_params["media_resolution"] = media_resolution
    
    if safety_settings:
        config_params["safety_settings"] = safety_settings

    config_with_system = types.GenerateContentConfig(**config_params)
    
    for retry_attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config_with_system
            )
            return _process_response(response, step_name, verbose)
            
        except Exception as e:
            error_msg = str(e)
            is_retriable = any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "overloaded"])
            
            if is_retriable and retry_attempt < MAX_RETRIES - 1:
                wait_time = 10 * (2 ** retry_attempt) if ("429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg) else (2 ** retry_attempt)
                time.sleep(wait_time + random.uniform(0, wait_time * 0.1))
            else:
                return f"Error: ❌ [{step_name}] API 호출 오류: {e}", None
                
    return "Error: All retries exhausted", None


def call_gemini_text(
    client: Client,
    model_name: str,
    prompt: str,
    step_name: str = "Text",
    verbose: bool = False,
    temperature: float = 0.3,
    thinking_level: str = "medium"
) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Gemini Text API 호출 (Stateless & Pure)
    """
    if client is None:
        return "Error: Client is required for call_gemini_text", None

    MAX_RETRIES = 3
    config_dict = {"temperature": temperature}
    
    thinking_cfg = get_thinking_config(model_name, thinking_level)
    if thinking_cfg:
        config_dict["thinking_config"] = thinking_cfg
        
    config_with_system = types.GenerateContentConfig(**config_dict)
    
    for retry_attempt in range(MAX_RETRIES):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt],
                config=config_with_system
            )
            return _process_response(response, step_name, verbose)
            
        except Exception as e:
            error_msg = str(e)
            is_retriable = any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "overloaded"])
            
            if is_retriable and retry_attempt < MAX_RETRIES - 1:
                wait_time = 10 * (2 ** retry_attempt) if ("429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg) else (2 ** retry_attempt)
                time.sleep(wait_time + random.uniform(0, wait_time * 0.1))
            else:
                return f"Error: ❌ [{step_name}] API 호출 오류: {e}", None

    return "Error: All retries exhausted", None


def parse_json_response(response_text: str) -> Dict[str, Any]:
    """
    응답 텍스트에서 JSON 추출 및 파싱 (Pure)
    """
    try:
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start != -1 and json_end > json_start:
            return json.loads(response_text[json_start:json_end])
        else:
            return {"error": "JSON 파싱 실패", "raw_response": response_text}
    except (json.JSONDecodeError, ValueError) as e:
        return {"error": f"JSON 파싱 오류: {e}", "raw_response": response_text}


def _process_response(response: Any, step_name: str, verbose: bool) -> Tuple[str, Optional[Dict[str, Any]]]:
    """응답 객체 처리 내부 헬퍼 (Stateless)"""
    try:
        thinking_info = {}
        response_text = getattr(response, 'text', "") or ""
        
        # Thinking 과정 추출
        executed_thought = ""
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'thought') and part.thought:
                            thought_val = part.thought
                            executed_thought += (str(thought_val) if not isinstance(thought_val, bool) else (part.text if hasattr(part, 'text') else "")) + "\n"
        
        if executed_thought.strip():
            thinking_info["reasoning_text"] = executed_thought.strip()
        elif response_text:
            json_start = response_text.find('{')
            if json_start > 0:
                thinking_text = response_text[:json_start].strip()
                if thinking_text:
                    thinking_info["reasoning_text"] = thinking_text

        if verbose:
            print(f"[{step_name}] Response processed successfully.")
            
        return response_text, thinking_info if thinking_info else None
    except Exception as e:
        return f"Error: Response processing failed: {e}", None


def load_image_data(image_path: str) -> bytes:
    """이미지 파일을 바이트로 로드 (Stateless)"""
    if not image_path or not os.path.exists(image_path):
        raise IOError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
    with open(image_path, "rb") as f:
        return f.read()
