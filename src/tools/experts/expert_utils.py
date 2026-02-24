"""
전문가 공통 유틸리티 함수
노트북들의 공통 함수를 통합하여 제공합니다.
"""
import os
import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
from google.genai import types
from dotenv import load_dotenv

# MediaResolution enum import
try:
    MediaResolution = types.MediaResolution
    # Check if ULTRA_HIGH is available (experimental feature)
    _has_ultra_high = hasattr(MediaResolution, 'MEDIA_RESOLUTION_ULTRA_HIGH')
except AttributeError:
    # Fallback if enum is not available
    class MediaResolution:
        MEDIA_RESOLUTION_UNSPECIFIED = "MEDIA_RESOLUTION_UNSPECIFIED"
        MEDIA_RESOLUTION_LOW = "MEDIA_RESOLUTION_LOW"
        MEDIA_RESOLUTION_MEDIUM = "MEDIA_RESOLUTION_MEDIUM"
        MEDIA_RESOLUTION_HIGH = "MEDIA_RESOLUTION_HIGH"
        MEDIA_RESOLUTION_ULTRA_HIGH = "MEDIA_RESOLUTION_HIGH"  # Fallback to HIGH
    _has_ultra_high = False
# from src.tools.experts.system_instructions import SYSTEM_INSTRUCTION

# .env 파일 로드
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

import config
from src.utils.genai_client import get_genai_client

# Google GenAI 설정 (config 또는 환경 변수)
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)

# Google GenAI Client 초기화 (Vertex AI 또는 Google AI Studio)
try:
    client = get_genai_client()
    generation_config = types.GenerateContentConfig(
        temperature=0.3,
        response_mime_type="application/json"
    )
except Exception as e:
    print(f"경고: Google GenAI 초기화 실패: {e}")
    client = None
    generation_config = None

def create_image_part(image_path: str) -> Optional[bytes]:
    """
    이미지 경로를 바이트 데이터로 변환
    
    Args:
        image_path: 이미지 파일 경로
        
    Returns:
        이미지 바이트 데이터 또는 None
    """
    if not os.path.exists(image_path):
        print(f"❌ 이미지 파일을 찾을 수 없습니다: {image_path}")
        return None
        
    try:
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
        return image_data
    except Exception as e:
        print(f"❌ 이미지 로드 오류: {e}")
        return None

def save_bytes_to_temp_file(image_data: bytes, suffix: str = '.jpg') -> str:
    """
    이미지 bytes 데이터를 임시 파일로 저장하고 경로 반환
    
    LangGraph 표준 패턴을 위해 bytes 데이터를 임시 파일로 저장합니다.
    임시 파일은 호출자가 수동으로 삭제해야 합니다.
    
    Args:
        image_data: 이미지 bytes 데이터
        suffix: 기본 파일 확장자 (이미지 형식 자동 감지 시 덮어씀)
        
    Returns:
        임시 파일 경로
    """
    import tempfile
    
    # 이미지 형식 자동 감지
    if len(image_data) >= 4 and image_data[:4] == b'\x89PNG':
        suffix = '.png'
    elif len(image_data) >= 3 and image_data[:3] == b'\xff\xd8\xff':
        suffix = '.jpg'
    
    # 임시 파일 생성 (delete=False로 설정하여 파일이 닫힌 후에도 유지)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        temp_file.write(image_data)
        temp_file_path = temp_file.name
    
    return temp_file_path

def extract_image_from_payload(payload: List[Any]) -> Optional[bytes]:
    """
    payload에서 이미지 데이터 추출
    기존 시스템의 payload 형식 지원
    
    Args:
        payload: LLM 입력 데이터 (이미지 + 텍스트)
        
    Returns:
        첫 번째 이미지 바이트 데이터 또는 None
    """
    import time
    
    
    if not payload:
        print("⚠️ payload가 비어있습니다.")
        return None
    
    for part in payload:
        if isinstance(part, dict) and "inline_data" in part:
            inline_data = part["inline_data"]
            try:
                
                image_data = base64.b64decode(inline_data["data"])
                
                return image_data
            except Exception as e:
                
                print(f"⚠️ payload에서 이미지 추출 실패: {e}")
                continue
    
    print("⚠️ payload에서 이미지 데이터를 찾을 수 없습니다.")
    return None

def call_gemini_vision(
    prompt: str, 
    image_data: list[bytes] | bytes, 
    step_name: str = "",
    verbose: bool = False,
    temperature: float = None,
    thinking_level: str = "medium",
    media_resolution: str | types.MediaResolution = None,
    model_name: str = None,
    safety_settings: Optional[List[Dict[str, str]]] = None,
    top_p: float = None,
    max_output_tokens: int = None,
    response_mime_type: str = None
) -> tuple[str, Optional[Dict]]:
    """
    Gemini Vision API 호출 및 에러 핸들링
    
    시스템 인스트럭션(부정적 제약 포함)을 자동으로 프롬프트에 추가합니다.
    이미지 데이터는 Base64로 인코딩하여 전달합니다 (Gemini API 권장 방식).
    
    Args:
        prompt: 분석 프롬프트
        image_data: 이미지 바이트 데이터 (단일 bytes 또는 bytes 리스트)
        step_name: 단계 이름 (로깅용)
        verbose: 상세 로그 출력 여부
        temperature: 온도 파라미터 (기본값: None, 이 경우 0.7 사용)
        thinking_level: 추론 레벨 ("high", "medium", "low", "minimal") 기본값: "medium"
        media_resolution: 이미지 해상도 ("MEDIA_RESOLUTION_ULTRA_HIGH", "MEDIA_RESOLUTION_HIGH", etc.) 기본값: None
        model_name: 사용할 모델 이름 (기본값: None, 이 경우 전역 MODEL_NAME 사용)
        safety_settings: 안전 설정 리스트 (기본값: None, 이 경우 사용 안 함)
        top_p: Top-p 샘플링 파라미터 (기본값: None, 이 경우 사용 안 함)
        max_output_tokens: 최대 출력 토큰 수 (기본값: None, 이 경우 사용 안 함)
        response_mime_type: 응답 MIME 타입 (기본값: None, 이 경우 사용 안 함)
        
    Returns:
        tuple: (response_text, thinking_info)
    """
    import time
    if client is None:
        error_msg = f"❌ [{step_name}] Client가 초기화되지 않았습니다."
        return f"Error: {error_msg}", None

    # 🔥 Retry Logic with Exponential Backoff
    MAX_RETRIES = 3
    response = None
    
    for retry_attempt in range(MAX_RETRIES):
        try:
            # contents 구성
            contents = [prompt]
            
            # image_data가 리스트가 아니면 리스트로 변환
            if not isinstance(image_data, list):
                image_data = [image_data]
                
            # 각 이미지 처리
            for img_bytes in image_data:
                if not img_bytes:
                    continue
                    
                # 이미지 MIME 타입 자동 감지 (PNG/JPEG)
                if len(img_bytes) >= 4 and img_bytes[:4] == b'\x89PNG':
                    mime_type = "image/png"
                elif len(img_bytes) >= 3 and img_bytes[:3] == b'\xff\xd8\xff':
                    mime_type = "image/jpeg"
                else:
                    mime_type = "image/png"  # 기본값
                
                # Base64 인코딩
                image_base64 = base64.b64encode(img_bytes).decode('utf-8')
                
                # contents에 이미지 파트 추가
                contents.append({
                    "inline_data": {
                        "mime_type": mime_type,
                        "data": image_base64
                    }
                })
            
            # 최신 SDK 방식: Client를 사용하여 콘텐츠 생성
            # Config 구성
            actual_model_name = model_name if model_name else MODEL_NAME
            thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
            
            config_params = {
                "temperature": temperature if temperature is not None else (generation_config.temperature if generation_config else 0.7)
            }
            
            # thinking level 지원 모델에만 추가
            if any(m in actual_model_name for m in thinking_supported_models):
                config_params["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
            
            # top_p가 지정된 경우 추가
            if top_p is not None:
                config_params["top_p"] = top_p
            
            # max_output_tokens가 지정된 경우 추가
            if max_output_tokens is not None:
                config_params["max_output_tokens"] = max_output_tokens
            
            # response_mime_type이 지정된 경우 추가
            if response_mime_type is not None:
                config_params["response_mime_type"] = response_mime_type
            
            # media_resolution이 지정된 경우에만 추가
            if media_resolution:
                # 문자열을 enum으로 변환
                if isinstance(media_resolution, str):
                    # 문자열을 MediaResolution enum 값으로 변환
                    # "high" 문자열도 지원 (Gemini 3 Pro 가이드)
                    resolution_map = {
                        "high": MediaResolution.MEDIA_RESOLUTION_HIGH,  # Gemini 3 Pro 가이드 형식
                        "MEDIA_RESOLUTION_LOW": MediaResolution.MEDIA_RESOLUTION_LOW,
                        "MEDIA_RESOLUTION_MEDIUM": MediaResolution.MEDIA_RESOLUTION_MEDIUM,
                        "MEDIA_RESOLUTION_HIGH": MediaResolution.MEDIA_RESOLUTION_HIGH,
                        "MEDIA_RESOLUTION_ULTRA_HIGH": getattr(
                            MediaResolution, 
                            'MEDIA_RESOLUTION_ULTRA_HIGH', 
                            MediaResolution.MEDIA_RESOLUTION_HIGH  # Fallback if not available
                        ),
                    }
                    config_params["media_resolution"] = resolution_map.get(media_resolution, MediaResolution.MEDIA_RESOLUTION_HIGH)
                else:
                    config_params["media_resolution"] = media_resolution
            
            # safety_settings가 지정된 경우에만 추가
            if safety_settings is not None:
                config_params["safety_settings"] = safety_settings
            
            config_with_system = types.GenerateContentConfig(**config_params)
            
            # 모델 이름 결정: 파라미터로 전달된 경우 사용, 없으면 전역 MODEL_NAME 사용
            used_model_name = model_name if model_name else MODEL_NAME
            
            call_start_time = time.time()
            response = client.models.generate_content(
                model=used_model_name,
                contents=contents,
                config=config_with_system
            )
            call_duration_ms = (time.time() - call_start_time) * 1000
            
            # Rate Limit 헤더 모니터링 (있는 경우)
            if verbose:
                # Gemini SDK 응답 객체에서 헤더 접근 시도
                # SDK 버전에 따라 헤더 접근 방식이 다를 수 있음
                try:
                    # 일반적인 헤더 접근 방식들 시도
                    headers = None
                    if hasattr(response, 'headers'):
                        headers = response.headers
                    elif hasattr(response, '_headers'):
                        headers = response._headers
                    elif hasattr(response, 'metadata') and hasattr(response.metadata, 'headers'):
                        headers = response.metadata.headers
                    
                    if headers:
                        # 딕셔너리 형태인 경우
                        if isinstance(headers, dict):
                            rate_limit_remaining = headers.get('X-RateLimit-Remaining') or headers.get('x-ratelimit-remaining')
                            rate_limit_reset = headers.get('X-RateLimit-Reset') or headers.get('x-ratelimit-reset')
                            rate_limit_limit = headers.get('X-RateLimit-Limit') or headers.get('x-ratelimit-limit')
                        else:
                            # 다른 형태의 헤더 객체인 경우
                            rate_limit_remaining = getattr(headers, 'X-RateLimit-Remaining', None) or getattr(headers, 'x-ratelimit-remaining', None)
                            rate_limit_reset = getattr(headers, 'X-RateLimit-Reset', None) or getattr(headers, 'x-ratelimit-reset', None)
                            rate_limit_limit = getattr(headers, 'X-RateLimit-Limit', None) or getattr(headers, 'x-ratelimit-limit', None)
                        
                        if rate_limit_remaining is not None:
                            print(f"📊 [Rate Limit] Remaining: {rate_limit_remaining}/{rate_limit_limit or 'N/A'}")
                            if rate_limit_reset:
                                print(f"📊 [Rate Limit] Reset at: {rate_limit_reset}")
                except Exception as header_err:
                    # 헤더 접근 실패는 무시 (SDK 버전 차이로 인한 정상적인 경우)
                    pass
            
            # 성공 시 루프 탈출
            break
            
        except Exception as e:
            error_msg = str(e)
            # 재시도 가능한 오류 판별
            is_retriable = any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "overloaded"])
            
            if is_retriable and retry_attempt < MAX_RETRIES - 1:
                import random
                # 429/RESOURCE_EXHAUSTED: 10s, 20s, 40s (retry_utils와 동일)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait_time = 10 * (2 ** retry_attempt)
                else:
                    wait_time = 2 ** retry_attempt  # 1초, 2초, 4초 (기타)
                jitter = random.uniform(0, wait_time * 0.1)  # 최대 10% 랜덤 추가
                total_wait = wait_time + jitter
                print(f"⚠️ [{step_name}] Retry {retry_attempt + 1}/{MAX_RETRIES}: {error_msg}")
                print(f"⏰ Waiting {total_wait:.2f}s (base: {wait_time}s + jitter: {jitter:.2f}s)...")
                time.sleep(total_wait)
            else:
                # 재시도 불가능하거나 최종 실패
                error_msg = f"❌ [{step_name}] API 호출 오류: {e}"
                if verbose:
                    import traceback
                    traceback.print_exc()
                return f"Error: {error_msg}", None
    
    # 모든 재시도 실패
    if response is None:
        error_msg = f"❌ [{step_name}] All retries exhausted"
        return f"Error: {error_msg}", None
    
    # 정상 응답 처리
    try:
        # Thinking 과정 추출 및 출력
        thinking_info = None
        response_text = ""
        full_response_text = ""
        
        # 최신 SDK 방식: response.text 직접 사용
        if hasattr(response, 'text') and response.text:
            response_text = response.text
            full_response_text = response.text
        
        # 응답 메타데이터 확인 (최신 SDK)
        if verbose and hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            
            # Finish reason 확인 (디버깅용)
            if hasattr(candidate, 'finish_reason'):
                finish_reason = candidate.finish_reason
                if finish_reason:
                    print(f"📋 [{step_name}] Finish reason: {finish_reason}")
        
        # 전체 응답 텍스트 출력 (thinking 과정이 포함되어 있을 수 있음)
        if full_response_text and len(full_response_text) > len(response_text):
            thinking_info = thinking_info or {}
            thinking_info["full_response"] = full_response_text
            if verbose:
                print(f"\n💭 [{step_name}] 전체 응답 텍스트 (thinking 과정 포함 가능):")
                print("-" * 60)
                print(full_response_text[:2000])  # 처음 2000자만 출력
                if len(full_response_text) > 2000:
                    print(f"... (총 {len(full_response_text)}자, 나머지 생략)")
                print("-" * 60)
        
        # 응답 텍스트 항상 출력 (JSON 파싱 전에 전체 응답 확인)
        # Thinking 과정 추출 (candidates.content.parts에서 'thought' 필드 또는 'thought=True' 확인)
        executed_thought = ""
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts:
                    for part in candidate.content.parts:
                        # part.thought가 존재하는지 확인
                        if hasattr(part, 'thought') and part.thought:
                            if isinstance(part.thought, bool):
                                # thought가 boolean True인 경우, 해당 파트의 text가 생각일 수 있음
                                if part.thought is True and hasattr(part, 'text') and part.text:
                                    executed_thought += part.text + "\n"
                            else:
                                # thought가 문자열인 경우
                                executed_thought += str(part.thought) + "\n"
        
        # 응답 텍스트 항상 출력 (JSON 파싱 전에 전체 응답 확인)
        if verbose:
            print(f"\n💭 [{step_name}] 모델 응답 텍스트:")
            print("-" * 60)
            
            # 1. SDK에서 추출한 Thought가 있는 경우 우선 출력
            if executed_thought and executed_thought.strip() != "True":
                print("📝 [Thinking 과정 (SDK Extracted)]:")
                print(executed_thought.strip())
                print("\n📄 [JSON 응답]:")
                
                # JSON 부분이 response_text에 있다면 출력
                json_start = response_text.find('{')
                if json_start >= 0:
                    print(response_text[json_start:json_start+1000])
                    if len(response_text[json_start:]) > 1000:
                        print(f"... (총 {len(response_text[json_start:])}자)")
                else:
                    print(response_text[:1000])
                    if len(response_text) > 1000:
                        print(f"... (총 {len(response_text)}자)")

            # 2. 없으면 기존 방식으로 텍스트에서 파싱 시도
            else:
                # 마크다운 코드 블록 제거 후 JSON 찾기
                cleaned_text = response_text.replace("```json", "").replace("```", "").strip()
                
                # JSON 시작 전까지의 텍스트 확인 (thinking 과정일 수 있음)
                json_start = cleaned_text.find('{')
                if json_start > 0:
                    thinking_part = cleaned_text[:json_start].strip()
                    
                    if thinking_part:
                        print("📝 [Thinking 과정]:")
                        print(thinking_part)
                        print("\n📄 [JSON 응답]:")
                        print(cleaned_text[json_start:json_start+500])
                        if len(cleaned_text[json_start:]) > 500:
                            print(f"... (총 {len(cleaned_text[json_start:])}자)")
                    else:
                        # thinking이 없고 바로 JSON만 있는 경우
                        print(cleaned_text[:1000])
                        if len(cleaned_text) > 1000:
                            print(f"... (총 {len(cleaned_text)}자)")
                else:
                    print(cleaned_text[:1000])
                    if len(cleaned_text) > 1000:
                        print(f"... (총 {len(cleaned_text)}자)")

            print("-" * 60)
        
        # 추출된 Thinking 과정 반환 (JSON 앞부분 텍스트)
        # 추출된 Thinking 과정 반환
        if executed_thought:
            if thinking_info is None:
                thinking_info = {}
            thinking_info["reasoning_text"] = executed_thought
        elif response_text:
            json_start = response_text.find('{')
            if json_start > 0:
                thinking_text = response_text[:json_start].strip()
                if thinking_text:
                    if thinking_info is None:
                        thinking_info = {}
                    thinking_info["reasoning_text"] = thinking_text

        return response_text, thinking_info
    except Exception as e:
        error_msg = f"❌ [{step_name}] 응답 처리 오류: {e}"
        if verbose:
            import traceback
            traceback.print_exc()
        return f"Error: {error_msg}", None

def parse_json_response(response_text: str) -> Dict[str, Any]:
    """
    응답 텍스트에서 JSON 추출 및 파싱
    
    Args:
        response_text: 모델 응답 텍스트
        
    Returns:
        파싱된 JSON 딕셔너리
    """
    try:
        # JSON 부분만 추출 (마크다운 코드 블록 제거)
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start != -1 and json_end > json_start:
            json_text = response_text[json_start:json_end]
            return json.loads(json_text)
        else:
            print(f"⚠️ 유효한 JSON을 찾을 수 없습니다. 원본 응답:\n{response_text[:100]}...")
            return {"error": "JSON 파싱 실패", "raw_response": response_text}
    except json.JSONDecodeError as e:
        print(f"⚠️ JSON 디코딩 오류: {e}")
        return {"error": f"JSON 파싱 오류: {e}", "raw_response": response_text}


def call_gemini_text(
    prompt: str,
    step_name: str = "",
    verbose: bool = False,
    temperature: float = None,
    thinking_level: str = "medium"
) -> tuple[str, Optional[Dict]]:
    """
    Gemini Text API 호출 및 에러 핸들링 (이미지 없이 텍스트만)
    
    Args:
        prompt: 분석 프롬프트
        step_name: 단계 이름 (로깅용)
        verbose: 상세 로그 출력 여부
        temperature: 온도 파라미터 (기본값: None, 이 경우 0.7 사용)
        thinking_level: 추론 레벨 ("high", "medium", "low", "minimal") 기본값: "medium"
        
    Returns:
        tuple: (response_text, thinking_info)
    """
    import time
    if client is None:
        error_msg = f"❌ [{step_name}] Client가 초기화되지 않았습니다."
        return f"Error: {error_msg}", None

    # 🔥 Retry Logic with Exponential Backoff
    MAX_RETRIES = 3
    response = None
    
    for retry_attempt in range(MAX_RETRIES):
        try:
            # 시스템 인스트럭션을 config에 포함
            # system_instruction=SYSTEM_INSTRUCTION, # Removed per user request
            thinking_supported_models = ["gemini-2.0-flash-exp", "gemini-2.5-flash", "gemini-2.5-pro"]
            config_dict = {
                "temperature": temperature if temperature is not None else (generation_config.temperature if generation_config else 0.7)
            }
            
            # thinking level 지원 모델에만 추가
            if any(m in MODEL_NAME for m in thinking_supported_models):
                config_dict["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)
            
            config_with_system = types.GenerateContentConfig(**config_dict)
            
            call_start_time = time.time()
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[prompt],
                config=config_with_system
            )
            call_duration_ms = (time.time() - call_start_time) * 1000
            
            # Rate Limit 헤더 모니터링 (있는 경우)
            if verbose:
                # Gemini SDK 응답 객체에서 헤더 접근 시도
                # SDK 버전에 따라 헤더 접근 방식이 다를 수 있음
                try:
                    # 일반적인 헤더 접근 방식들 시도
                    headers = None
                    if hasattr(response, 'headers'):
                        headers = response.headers
                    elif hasattr(response, '_headers'):
                        headers = response._headers
                    elif hasattr(response, 'metadata') and hasattr(response.metadata, 'headers'):
                        headers = response.metadata.headers
                    
                    if headers:
                        # 딕셔너리 형태인 경우
                        if isinstance(headers, dict):
                            rate_limit_remaining = headers.get('X-RateLimit-Remaining') or headers.get('x-ratelimit-remaining')
                            rate_limit_reset = headers.get('X-RateLimit-Reset') or headers.get('x-ratelimit-reset')
                            rate_limit_limit = headers.get('X-RateLimit-Limit') or headers.get('x-ratelimit-limit')
                        else:
                            # 다른 형태의 헤더 객체인 경우
                            rate_limit_remaining = getattr(headers, 'X-RateLimit-Remaining', None) or getattr(headers, 'x-ratelimit-remaining', None)
                            rate_limit_reset = getattr(headers, 'X-RateLimit-Reset', None) or getattr(headers, 'x-ratelimit-reset', None)
                            rate_limit_limit = getattr(headers, 'X-RateLimit-Limit', None) or getattr(headers, 'x-ratelimit-limit', None)
                        
                        if rate_limit_remaining is not None:
                            print(f"📊 [Rate Limit] Remaining: {rate_limit_remaining}/{rate_limit_limit or 'N/A'}")
                            if rate_limit_reset:
                                print(f"📊 [Rate Limit] Reset at: {rate_limit_reset}")
                except Exception as header_err:
                    # 헤더 접근 실패는 무시 (SDK 버전 차이로 인한 정상적인 경우)
                    pass
            
            # 성공 시 루프 탈출
            break
            
        except Exception as e:
            error_msg = str(e)
            # 재시도 가능한 오류 판별
            is_retriable = any(code in error_msg for code in ["503", "429", "UNAVAILABLE", "overloaded"])
            
            if is_retriable and retry_attempt < MAX_RETRIES - 1:
                import random
                # 429/RESOURCE_EXHAUSTED: 10s, 20s, 40s (retry_utils와 동일)
                if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    wait_time = 10 * (2 ** retry_attempt)
                else:
                    wait_time = 2 ** retry_attempt  # 1초, 2초, 4초 (기타)
                jitter = random.uniform(0, wait_time * 0.1)  # 최대 10% 랜덤 추가
                total_wait = wait_time + jitter
                print(f"⚠️ [{step_name}] Retry {retry_attempt + 1}/{MAX_RETRIES}: {error_msg}")
                print(f"⏰ Waiting {total_wait:.2f}s (base: {wait_time}s + jitter: {jitter:.2f}s)...")
                time.sleep(total_wait)
            else:
                # 재시도 불가능하거나 최종 실패
                error_msg = f"❌ [{step_name}] API 호출 오류: {e}"
                if verbose:
                    import traceback
                    traceback.print_exc()
                return f"Error: {error_msg}", None
    
    # 모든 재시도 실패
    if response is None:
        error_msg = f"❌ [{step_name}] All retries exhausted"
        return f"Error: {error_msg}", None
    
    # 정상 응답 처리
    try:
        # Thinking 과정 추출 및 출력 (Vision 함수와 동일 로직)
        thinking_info = None
        response_text = ""
        full_response_text = ""
        
        # 최신 SDK 방식: response.text 직접 사용
        if hasattr(response, 'text') and response.text:
            response_text = response.text
            full_response_text = response.text
        
        # 응답 메타데이터 확인 (최신 SDK)
        if verbose and hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'finish_reason') and candidate.finish_reason:
                print(f"📋 [{step_name}] Finish reason: {candidate.finish_reason}")
        
        # 전체 응답 텍스트 출력
        if full_response_text and len(full_response_text) > len(response_text):
            thinking_info = thinking_info or {}
            thinking_info["full_response"] = full_response_text
            if verbose:
                print(f"\n💭 [{step_name}] 전체 응답 텍스트 (thinking 과정 포함 가능):")
                print("-" * 60)
                print(full_response_text[:2000])
                if len(full_response_text) > 2000:
                    print(f"... (총 {len(full_response_text)}자, 나머지 생략)")
                print("-" * 60)
        
        # 응답 텍스트 항상 출력
        # Thinking 과정 추출 (candidates.content.parts에서 'thought' 필드 확인)
        executed_thought = ""
        if hasattr(response, 'candidates') and response.candidates:
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and candidate.content and hasattr(candidate.content, 'parts') and candidate.content.parts:
                    for part in candidate.content.parts:
                        # part.thought가 존재하는지 확인
                        if hasattr(part, 'thought') and part.thought:
                            if isinstance(part.thought, bool):
                                # thought가 boolean True인 경우, 해당 파트의 text가 생각일 수 있음
                                if part.thought is True and hasattr(part, 'text') and part.text:
                                    executed_thought += part.text + "\n"
                            else:
                                # thought가 문자열인 경우
                                executed_thought += str(part.thought) + "\n"

        # 응답 텍스트 항상 출력
        if verbose:
            print(f"\n💭 [{step_name}] 모델 응답 텍스트:")
            print("-" * 60)
            
            # 1. SDK에서 추출한 Thought가 있는 경우 우선 출력
            if executed_thought and executed_thought.strip() != "True":
                print("📝 [Thinking 과정 (SDK Extracted)]:")
                print(executed_thought.strip())
                print("\n📄 [JSON 응답]:")
                # JSON 부분이 response_text에 있다면 출력
                json_start = response_text.find('{')
                if json_start >= 0:
                    print(response_text[json_start:json_start+1000])
                    if len(response_text[json_start:]) > 1000:
                        print(f"... (총 {len(response_text[json_start:])}자)")
                else:
                    print(response_text[:1000])
                    if len(response_text) > 1000:
                        print(f"... (총 {len(response_text)}자)")
            
            # 2. 없으면 기존 방식으로 텍스트에서 파싱 시도
            else:
                json_start = response_text.find('{')
                if json_start > 0:
                    thinking_part = response_text[:json_start].strip()
                    # 마크다운 코드 블록 잔여물 제거 (```json 등)
                    thinking_part = thinking_part.replace("```json", "").replace("```", "").strip()
                    
                    if thinking_part:
                        print("📝 [Thinking 과정]:")
                        print(thinking_part)
                        print("\n📄 [JSON 응답]:")
                        print(response_text[json_start:json_start+500])
                        if len(response_text[json_start:]) > 500:
                            print(f"... (총 {len(response_text[json_start:])}자)")
                    else:
                        print(response_text[:1000])
                else:
                    print(response_text[:1000])
            print("-" * 60)
        
        # 추출된 Thinking 과정 반환
        # 추출된 Thinking 과정 반환
        if executed_thought:
            if thinking_info is None:
                thinking_info = {}
            thinking_info["reasoning_text"] = executed_thought
        elif response_text:
            json_start = response_text.find('{')
            if json_start > 0:
                thinking_text = response_text[:json_start].strip()
                if thinking_text:
                    if thinking_info is None:
                        thinking_info = {}
                    thinking_info["reasoning_text"] = thinking_text

        return response_text, thinking_info
    except Exception as e:
        error_msg = f"❌ [{step_name}] 응답 처리 오류: {e}"
        if verbose:
            import traceback
            traceback.print_exc()
        return f"Error: {error_msg}", None

def _load_image_data(image_path: str) -> bytes:
    """이미지 파일을 바이트로 로드"""
    if not image_path or not os.path.exists(image_path):
        raise IOError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
    try:
        with open(image_path, "rb") as f:
            return f.read()
    except Exception as e:
        raise IOError(f"이미지 로드 실패: {str(e)}")

