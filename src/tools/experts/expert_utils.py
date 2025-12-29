"""
전문가 공통 유틸리티 함수
노트북들의 공통 함수를 통합하여 제공합니다.
"""
import os
import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
from google import genai
from google.genai import types
from dotenv import load_dotenv
from src.tools.experts.system_instructions import SYSTEM_INSTRUCTION

# .env 파일 로드
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Google GenAI 설정
API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

# Google GenAI Client 초기화 (최신 SDK 방식)
if API_KEY:
    try:
        client = genai.Client(api_key=API_KEY)
        generation_config = types.GenerateContentConfig(
            temperature=0.3,
            response_mime_type="application/json"
        )
    except Exception as e:
        print(f"경고: Google GenAI 초기화 실패: {e}")
        client = None
        generation_config = None
else:
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
    image_data: bytes, 
    step_name: str = "",
    verbose: bool = False
) -> tuple[str, Optional[Dict]]:
    """
    Gemini Vision API 호출 및 에러 핸들링
    
    시스템 인스트럭션(부정적 제약 포함)을 자동으로 프롬프트에 추가합니다.
    
    Args:
        prompt: 분석 프롬프트
        image_data: 이미지 바이트 데이터
        step_name: 단계 이름 (로깅용)
        verbose: 상세 로그 출력 여부
        
    Returns:
        tuple: (response_text, thinking_info)
    """
    import time
    if client is None:
        error_msg = f"❌ [{step_name}] Client가 초기화되지 않았습니다."
        return f"Error: {error_msg}", None

    try:
        
        # 이미지 MIME 타입 자동 감지 (PNG/JPEG)
        # PNG 시그니처 확인: 89 50 4E 47 (0x89 0x50 0x4E 0x47)
        # JPEG 시그니처 확인: FF D8 FF
        if len(image_data) >= 4 and image_data[:4] == b'\x89PNG':
            mime_type = "image/png"
        elif len(image_data) >= 3 and image_data[:3] == b'\xff\xd8\xff':
            mime_type = "image/jpeg"
        else:
            mime_type = "image/png"  # 기본값
        
        # 최신 SDK 방식: Client를 사용하여 콘텐츠 생성
        # 시스템 인스트럭션을 config에 포함 (노트북 방식)
        config_with_system = types.GenerateContentConfig(
            temperature=generation_config.temperature if generation_config else 0.7,
            system_instruction=SYSTEM_INSTRUCTION,
        )
        
        call_start_time = time.time()
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt,
                types.Part.from_bytes(data=image_data, mime_type=mime_type)
            ],
            config=config_with_system
        )
        call_duration_ms = (time.time() - call_start_time) * 1000
        
        
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
        if verbose and response_text:
            print(f"\n💭 [{step_name}] 모델 응답 텍스트:")
            print("-" * 60)
            # JSON 시작 전까지의 텍스트 확인 (thinking 과정일 수 있음)
            json_start = response_text.find('{')
            if json_start > 0:
                thinking_part = response_text[:json_start].strip()
                if thinking_part:
                    print("📝 [Thinking 과정]:")
                    print(thinking_part)
                    print("\n📄 [JSON 응답]:")
                    print(response_text[json_start:json_start+500])
                    if len(response_text[json_start:]) > 500:
                        print(f"... (총 {len(response_text[json_start:])}자)")
                else:
                    print(response_text[:1000])
                    if len(response_text) > 1000:
                        print(f"... (총 {len(response_text)}자)")
            else:
                print(response_text[:1000])
                if len(response_text) > 1000:
                    print(f"... (총 {len(response_text)}자)")
            print("-" * 60)
        
        # 추출된 Thinking 과정 반환 (JSON 앞부분 텍스트)
        if response_text:
            json_start = response_text.find('{')
            if json_start > 0:
                thinking_text = response_text[:json_start].strip()
                if thinking_text:
                    if thinking_info is None:
                        thinking_info = {}
                    thinking_info["reasoning_text"] = thinking_text

        return response_text, thinking_info
    except Exception as e:
        
        error_msg = f"❌ [{step_name}] API 호출 오류: {e}"
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

