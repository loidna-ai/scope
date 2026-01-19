"""
공통 노드 정의
모든 전문가가 공통으로 사용하는 노드들
"""
from typing import Dict, Any
import tempfile
import os
from src.state import InvestigationState
from src.tools.experts.expert_utils import (
    extract_image_from_payload,
    save_bytes_to_temp_file,
    _load_image_data
)
from src.prompts.common_prompts import get_multi_hotspot_prompt



def hotspot_detector_node(state: InvestigationState) -> Dict[str, Any]:
    """
    공통 Hotspot Detector 노드
    InvestigationState를 사용하여 전체 이미지에서 다중 발화 지점(Hotspots) 탐색
    
    Args:
        state: InvestigationState (payload 포함)
        
    Returns:
        {"hotspots": List[Dict]} - 탐지된 Hotspot 리스트
    """
    # [Memory Optimization] image_path 우선 사용
    image_path = state.get("image_path")
    temp_image_path = None
    should_cleanup = False
    
    if image_path and os.path.exists(image_path):
        print(f"📂 [Hotspot Detector] 이미지 경로 감지: {image_path}")
        temp_image_path = image_path
    else:
        # Fallback: payload 사용 (기존 로직)
        payload = state.get("payload", [])
        if not payload:
            print("⚠️ [Hotspot Detector] payload가 비어있고 image_path도 없습니다.")
            return {"hotspots": []}
        
        image_data = extract_image_from_payload(payload)
        if image_data is None:
            print("⚠️ [Hotspot Detector] payload에서 이미지를 추출할 수 없습니다.")
            return {"hotspots": []}
            
        temp_image_path = save_bytes_to_temp_file(image_data)
        should_cleanup = True # 임시 파일이므로 정리 필요
    
    try:
        print(f"\n📡 [Hotspot Detector] 다중 발화 지점 탐색 시작... (이미지: {temp_image_path})")
        
        # 이미지 데이터 로드
        image_data_bytes = _load_image_data(temp_image_path)
        
        # 프롬프트 생성
        prompt = get_multi_hotspot_prompt(temp_image_path)
        
        # 🔥 Pydantic Structured Output (Gemini Official Best Practice)
        from src.models.hotspot_models import HotspotDetectionResult
        from google import genai
        from google.genai import types
        
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        
        # 이미지 파트 구성 (고해상도 설정)
        image_part = types.Part.from_bytes(
            data=image_data_bytes,
            mime_type="image/jpeg"
        )
        
        # Safety settings
        safety_settings_block_none = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        
        # 🔥 Retry Logic with Exponential Backoff
        MAX_RETRIES = 3
        response = None
        
        for retry_attempt in range(MAX_RETRIES):
            # Structured Output API 호출 (공식 권장 방식)
            # GEMINI_MODEL_NAME 또는 gemini-3-flash-preview 사용
            model_name = os.environ.get("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
            response = client.models.generate_content(
                model=model_name,
                contents=[prompt, image_part],
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": HotspotDetectionResult.model_json_schema(),
                    # "temperature": 1.0,  # Thinking 모드에서는 temperature 설정이 권장되지 않음
                    # "top_p": 0.95,
                    "max_output_tokens": 8192,
                    "media_resolution": "MEDIA_RESOLUTION_HIGH",
                    "safety_settings": safety_settings_block_none,
                    "thinking_config": {
                        "include_thoughts": True,
                        "thinking_level": "HIGH"  # Thinking Level: High (복잡한 시각적 특징 분석)
                    }
                }
            )
            
            # [Debug/Safety] 응답 텍스트 확인 및 안전 파싱
            response_text = getattr(response, 'text', None)
            
            if response_text:
                # 성공 시 루프 탈출
                break
                
            # 응답이 비어있는 경우 재시도 처리
            finish_reason = "Unknown"
            if hasattr(response, 'candidates') and response.candidates:
                finish_reason = getattr(response.candidates[0], 'finish_reason', "Unknown")
            
            if retry_attempt < MAX_RETRIES - 1:
                import time
                import random
                wait_time = 2 ** retry_attempt  # 1s, 2s, 4s
                jitter = random.uniform(0, wait_time * 0.1)
                total_wait = wait_time + jitter
                print(f"⚠️ [Hotspot Detector] 응답 누락으로 재시도 중... ({retry_attempt + 1}/{MAX_RETRIES})")
                print(f"   - Finish Reason: {finish_reason}, 대기: {total_wait:.2f}s")
                time.sleep(total_wait)
            else:
                error_msg = f"Gemini API 응답이 비어있습니다. (Finish Reason: {finish_reason})"
                print(f"❌ [Hotspot Detector] {error_msg}")
                return {"hotspots": [], "errors": [error_msg]}

        # Pydantic 안전 파싱 (공식 권장 방식)
        try:
            detection_result = HotspotDetectionResult.model_validate_json(response_text)
            
            # Hotspot 리스트 추출
            hotspots = [h.model_dump() for h in detection_result.hotspots]
            
            print(f"✅ [Hotspot Detector] 발견된 Hotspots: {len(hotspots)}개")
            for h in hotspots:
                print(f"   - ID {h.get('id')}: {h.get('damage_type')} (Score: {h.get('severity_score')})")
            
            return {"hotspots": hotspots}
        except Exception as pydantic_err:
            print(f"❌ [Hotspot Detector] Pydantic 파싱 오류: {pydantic_err}")
            print(f"🔍 [Raw Response]: {response_text}")
            return {"hotspots": [], "errors": [f"데이터 파싱 오류: {str(pydantic_err)}"]}



        
    except Exception as e:
        import traceback
        print(f"❌ [Hotspot Detector] 오류 발생: {str(e)}")
        traceback.print_exc()
        return {"hotspots": []}
    finally:
        # 임시 파일 정리
        # 임시 파일 정리 (우리가 생성한 경우만)
        if should_cleanup and temp_image_path and os.path.exists(temp_image_path):
            try:
                os.remove(temp_image_path)
            except Exception:
                pass

