"""
화재조사 멀티 에이전트 노드
5명의 전문가와 수석 조사관 노드를 구현합니다.
"""
import os
import base64
from typing import Dict, Optional
from pathlib import Path
from dotenv import load_dotenv
import vertexai
from vertexai.generative_models import GenerativeModel, Part, GenerationConfig
from src.state import InvestigationState

# .env 파일 로드 (프로젝트 루트에서)
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Vertex AI 설정
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL_NAME = "gemini-2.0-flash-exp"  # Vertex AI 모델 이름

# Vertex AI 초기화 및 GenerativeModel 생성
if PROJECT_ID:
    try:
        # Vertex AI 초기화
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        # GenerativeModel 초기화
        model = GenerativeModel(MODEL_NAME)
        generation_config = GenerationConfig(
            temperature=0.7,
        )
    except Exception as e:
        print(f"경고: Vertex AI 초기화 실패: {e}")
        model = None
        generation_config = None
else:
    model = None
    generation_config = None


# 전문가 프롬프트 정의
TRACKING_PROMPT = """당신은 화재 추적 전문가입니다. 제공된 이미지와 데이터를 바탕으로 화재의 시작점과 확산 경로를 추적하여 상세 리포트를 작성하세요.

분석 항목:
1. 화재 시작점 추정 위치
2. 화재 확산 방향 및 경로
3. 연소 패턴 분석
4. 화재 진행 단계 추정

제공된 데이터를 객관적으로 분석하고, 전문가 관점에서 상세한 리포트를 작성해주세요."""


SHORT_CIRCUIT_PROMPT = """당신은 단락 전문가입니다. 제공된 이미지와 데이터를 바탕으로 단락 흔적을 분석하고, 단락이 화재 원인일 가능성에 대한 리포트를 작성하세요.

분석 항목:
1. 단락 흔적의 형태학적 특성 (원형도, 고형도, 면적)
2. 단락 발생 가능성 평가
3. 단락으로 인한 화재 가능성
4. 단락 원인 추정 (과부하, 절연 파괴, 이물질 등)

제공된 데이터를 객관적으로 분석하고, 전문가 관점에서 상세한 리포트를 작성해주세요."""


SEVERED_PROMPT = """당신은 절단 전문가입니다. 제공된 이미지와 데이터를 바탕으로 전선 등의 절단 흔적을 분석하고, 절단이 화재 원인일 가능성에 대한 리포트를 작성하세요.

분석 항목:
1. 절단 흔적의 형태학적 특성
2. 절단 방법 추정 (기계적 절단, 화학적 절단 등)
3. 절단으로 인한 화재 가능성
4. 절단 시점 추정 (화재 전/후)

제공된 데이터를 객관적으로 분석하고, 전문가 관점에서 상세한 리포트를 작성해주세요."""


CONTACT_PROMPT = """당신은 접촉 전문가입니다. 제공된 이미지와 데이터를 바탕으로 전기 접촉 불량 또는 이물질 접촉으로 인한 화재 가능성에 대한 리포트를 작성하세요.

분석 항목:
1. 접촉 불량 흔적 분석
2. 이물질 접촉 가능성
3. 접촉 저항 증가로 인한 발열 가능성
4. 접촉 불량이 화재 원인일 가능성

제공된 데이터를 객관적으로 분석하고, 전문가 관점에서 상세한 리포트를 작성해주세요."""


OVERCURRENT_PROMPT = """당신은 과전류 전문가입니다. 제공된 이미지와 데이터를 바탕으로 과전류로 인한 화재 가능성을 분석하고 리포트를 작성하세요.

분석 항목:
1. 과전류 흔적 분석
2. 과전류 발생 원인 추정
3. 과전류로 인한 발열 및 화재 가능성
4. 보호 장치 동작 여부 추정

제공된 데이터를 객관적으로 분석하고, 전문가 관점에서 상세한 리포트를 작성해주세요."""


CHIEF_INVESTIGATOR_PROMPT = """당신은 화재조사 수석 조사관입니다. 5명의 전문가가 작성한 리포트를 종합하여 최종 결론을 도출하세요.

전문가 리포트:
{expert_reports}

다음 항목을 포함하여 최종 결론을 작성하세요:
1. 화재 원인 종합 분석
2. 각 전문가 의견의 일치/불일치 사항
3. 가장 가능성 높은 화재 원인
4. 추가 조사가 필요한 사항

명확하고 객관적인 최종 결론을 작성해주세요."""


def run_expert_node(
    state: InvestigationState,
    expert_prompt: str,
    expert_name: str
) -> Dict:
    """
    전문가 노드 공통 실행 함수
    
    Args:
        state: 그래프 상태
        expert_prompt: 전문가 프롬프트
        expert_name: 전문가 이름
    
    Returns:
        Partial State: {'expert_reports': [report]}
    """
    if model is None:
        error_msg = f"{expert_name} 전문가 노드 실행 실패: GOOGLE_CLOUD_PROJECT가 설정되지 않았습니다."
        return {
            "errors": [error_msg],
            "expert_reports": []
        }
    
    try:
        # payload를 Vertex AI Part 형식으로 변환
        # payload는 to_gemini_vertex_ai_format()에서 반환된 형식:
        # [text_string, {inline_data: {...}}, {inline_data: {...}}, ...]
        parts = []
        
        # 전문가 프롬프트를 첫 번째 텍스트로 추가
        combined_text = f"{expert_prompt}\n\n"
        
        # payload의 각 항목을 Part로 변환
        for part in state["payload"]:
            if isinstance(part, str):
                # 텍스트 부분
                combined_text += part + "\n\n"
            elif isinstance(part, dict) and "inline_data" in part:
                # 기존 텍스트가 있으면 먼저 추가
                if combined_text.strip():
                    parts.append(Part.from_text(combined_text.strip()))
                    combined_text = ""
                
                # 이미지 부분: Base64 데이터를 Part로 변환
                inline_data = part["inline_data"]
                image_data = base64.b64decode(inline_data["data"])
                mime_type = inline_data["mime_type"]
                parts.append(Part.from_data(image_data, mime_type=mime_type))
            else:
                # 기타 형식은 문자열로 변환
                combined_text += str(part) + "\n\n"
        
        # 남은 텍스트가 있으면 추가
        if combined_text.strip():
            combined_text += "위 프롬프트에 따라 제공된 데이터를 분석하여 리포트를 작성해주세요."
            parts.insert(0, Part.from_text(combined_text.strip()))
        else:
            # 텍스트가 없으면 프롬프트만 추가
            parts.insert(0, Part.from_text(f"{expert_prompt}\n\n위 프롬프트에 따라 제공된 데이터를 분석하여 리포트를 작성해주세요."))
        
        # Vertex AI 모델 호출
        response = model.generate_content(
            parts,
            generation_config=generation_config
        )
        
        # 리포트 추출
        report_text = response.text if hasattr(response, 'text') else str(response)
        report = f"[{expert_name} 전문가 리포트]\n{report_text}"
        
        return {
            "expert_reports": [report]
        }
    
    except Exception as e:
        error_msg = f"{expert_name} 전문가 노드 실행 중 오류 발생: {str(e)}"
        import traceback
        traceback.print_exc()
        return {
            "errors": [error_msg],
            "expert_reports": []
        }


def node_tracking(state: InvestigationState) -> Dict:
    """추적 전문가 노드"""
    return run_expert_node(state, TRACKING_PROMPT, "Tracking")


def node_short_circuit(state: InvestigationState) -> Dict:
    """단락 전문가 노드"""
    return run_expert_node(state, SHORT_CIRCUIT_PROMPT, "ShortCircuit")


def node_severed(state: InvestigationState) -> Dict:
    """절단 전문가 노드"""
    return run_expert_node(state, SEVERED_PROMPT, "Severed")


def node_contact(state: InvestigationState) -> Dict:
    """접촉 전문가 노드"""
    return run_expert_node(state, CONTACT_PROMPT, "Contact")


def node_overcurrent(state: InvestigationState) -> Dict:
    """과전류 전문가 노드"""
    return run_expert_node(state, OVERCURRENT_PROMPT, "Overcurrent")


def node_chief_investigator(state: InvestigationState) -> Dict:
    """
    수석 조사관 노드
    모든 전문가 리포트를 취합하여 최종 결론 도출
    
    Returns:
        Partial State: {'final_verdict': str}
    """
    if model is None:
        error_msg = "수석 조사관 노드 실행 실패: GOOGLE_CLOUD_PROJECT가 설정되지 않았습니다."
        return {
            "errors": [error_msg],
            "final_verdict": None
        }
    
    try:
        # 모든 전문가 리포트 수집
        expert_reports = state.get("expert_reports", [])
        
        if not expert_reports:
            return {
                "errors": ["수석 조사관 노드 실행 실패: 전문가 리포트가 없습니다."],
                "final_verdict": None
            }
        
        # 리포트들을 하나의 문자열로 결합
        reports_text = "\n\n".join(expert_reports)
        
        # 수석 조사관 프롬프트 생성
        chief_prompt = CHIEF_INVESTIGATOR_PROMPT.format(expert_reports=reports_text)
        
        # Vertex AI 모델 호출
        parts = [Part.from_text(chief_prompt)]
        response = model.generate_content(
            parts,
            generation_config=generation_config
        )
        
        # 최종 결론 반환
        final_verdict = response.text if hasattr(response, 'text') else str(response)
        return {
            "final_verdict": final_verdict
        }
    
    except Exception as e:
        error_msg = f"수석 조사관 노드 실행 중 오류 발생: {str(e)}"
        import traceback
        traceback.print_exc()
        return {
            "errors": [error_msg],
            "final_verdict": None
        }

