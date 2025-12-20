"""
전문가 공통 유틸리티 함수
노트북들의 공통 함수를 통합하여 제공합니다.
"""
import os
import json
import base64
from typing import Dict, Any, Optional, List
from pathlib import Path
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from dotenv import load_dotenv

# .env 파일 로드
env_path = Path(__file__).parent.parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Vertex AI 설정
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-pro")

# Vertex AI 초기화 및 GenerativeModel 생성
if PROJECT_ID:
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel(MODEL_NAME)
        generation_config = GenerationConfig(temperature=0.7)
    except Exception as e:
        print(f"경고: Vertex AI 초기화 실패: {e}")
        model = None
        generation_config = None
else:
    model = None
    generation_config = None


def create_image_part(image_path: str) -> Optional[Part]:
    """
    이미지 경로를 Vertex AI Part 객체로 변환
    
    Args:
        image_path: 이미지 파일 경로
        
    Returns:
        Part 객체 또는 None
    """
    if not os.path.exists(image_path):
        print(f"❌ 이미지 파일을 찾을 수 없습니다: {image_path}")
        return None
        
    try:
        with open(image_path, "rb") as image_file:
            image_data = image_file.read()
        
        # 확장자에 따른 MIME 타입 추론
        ext = Path(image_path).suffix.lower()
        mime_type = "image/png" if ext == ".png" else "image/jpeg"
        
        return Part.from_data(data=image_data, mime_type=mime_type)
    except Exception as e:
        print(f"❌ 이미지 로드 오류: {e}")
        return None


def extract_image_from_payload(payload: List[Any]) -> Optional[Part]:
    """
    payload에서 이미지 Part 추출
    기존 시스템의 payload 형식 지원
    
    Args:
        payload: LLM 입력 데이터 (이미지 + 텍스트)
        
    Returns:
        첫 번째 이미지 Part 객체 또는 None
    """
    if model is None:
        return None
    
    for part in payload:
        if isinstance(part, dict) and "inline_data" in part:
            inline_data = part["inline_data"]
            try:
                image_data = base64.b64decode(inline_data["data"])
                mime_type = inline_data["mime_type"]
                return Part.from_data(image_data, mime_type=mime_type)
            except Exception as e:
                print(f"⚠️ payload에서 이미지 추출 실패: {e}")
                continue
    
    return None


def call_gemini_vision(
    prompt: str, 
    image_part: Part, 
    step_name: str = "",
    verbose: bool = False
) -> tuple[str, Optional[Dict]]:
    """
    Gemini Vision API 호출 및 에러 핸들링
    
    Args:
        prompt: 분석 프롬프트
        image_part: 이미지 Part 객체
        step_name: 단계 이름 (로깅용)
        verbose: 상세 로그 출력 여부
        
    Returns:
        tuple: (response_text, thinking_info)
    """
    if model is None:
        error_msg = f"❌ [{step_name}] 모델이 초기화되지 않았습니다."
        return f"Error: {error_msg}", None
    
    try:
        response = model.generate_content([prompt, image_part], generation_config=generation_config)
        
        # Thinking 과정 추출 및 출력
        thinking_info = None
        response_text = ""
        full_response_text = ""
        
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            
            # 모든 파트 확인 (thinking 과정이 별도 파트로 있을 수 있음)
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                parts = candidate.content.parts
                if verbose:
                    print(f"\n🔍 [{step_name}] 응답 파트 개수: {len(parts)}")
                
                all_texts = []
                for i, part in enumerate(parts):
                    if hasattr(part, 'text'):
                        part_text = part.text
                        all_texts.append(part_text)
                        if i == 0:
                            # 첫 번째 파트는 일반 응답
                            response_text = part_text
                        else:
                            # 이후 파트는 thinking 과정일 수 있음
                            if part_text and part_text.strip():
                                thinking_info = thinking_info or {}
                                thinking_info[f"part_{i}"] = part_text
                                if verbose:
                                    print(f"\n💭 [{step_name}] 모델의 생각 과정 (파트 {i}):")
                                    print("-" * 60)
                                    print(part_text)
                                    print("-" * 60)
                
                # 모든 파트의 텍스트를 합쳐서 전체 응답 확인
                full_response_text = "\n\n".join(all_texts)
            
            # Grounding metadata 확인
            if hasattr(candidate, 'grounding_metadata'):
                grounding = candidate.grounding_metadata
                if grounding:
                    thinking_info = thinking_info or {}
                    thinking_info["grounding"] = str(grounding)
                    if verbose:
                        print(f"\n📚 [{step_name}] Grounding 정보: {grounding}")
            
            # Finish reason 확인 (디버깅용)
            if verbose and hasattr(candidate, 'finish_reason'):
                finish_reason = candidate.finish_reason
                if finish_reason:
                    print(f"📋 [{step_name}] Finish reason: {finish_reason}")
        
        # response.text가 있으면 사용 (fallback)
        if not response_text and hasattr(response, 'text'):
            response_text = response.text
        
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

