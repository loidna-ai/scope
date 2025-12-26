"""
전문가 서브그래프 조건부 엣지 함수
Step별로 ReAct 에이전트 호출 여부를 결정합니다.

LangGraph 공식 권장 방식:
- 조건부 엣지를 사용하여 동적 분기
- Step 결과의 신뢰도를 기반으로 ReAct 에이전트 호출 여부 결정
- 실제 도구 선택은 ReAct 에이전트 내부의 LLM이 판단

주의사항:
- 이 함수들은 ReAct 에이전트를 호출할지 말지만 결정합니다
- 어떤 도구를 사용할지는 ReAct 에이전트 내부의 LLM이 선택합니다
"""
from typing import Literal
from src.state import InvestigationState


def should_use_react_agent_contact_step1(state: InvestigationState) -> Literal["react_agent", "step2_spectral"]:
    """
    Contact Expert Step1 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    LLM이 상황을 판단하고 필요한 도구를 선택하게 함
    
    Returns:
        "react_agent": 추가 분석/이미지 편집 필요
        "step2_spectral": 다음 Step으로 진행
    """
    step1_result = state.get("contact_step1_result", {})
    
    # 에러가 있으면 다음 Step으로 진행
    if step1_result.get("error"):
        return "step2_spectral"
    
    # 신뢰도가 낮거나 결과가 불확실하면 react_agent 호출
    # LLM이 이미지 품질, 해상도 등을 판단하고 필요한 도구를 선택
    confidence = step1_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step2_spectral"


def should_use_react_agent_contact_step2(state: InvestigationState) -> Literal["react_agent", "step3_thermal"]:
    """
    Contact Expert Step2 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    LLM이 상황을 판단하고 필요한 도구를 선택하게 함
    
    Returns:
        "react_agent": 추가 분석/이미지 편집 필요
        "step3_thermal": 다음 Step으로 진행
    """
    step2_result = state.get("contact_step2_result", {})
    
    # 에러가 있으면 다음 Step으로 진행
    if step2_result.get("error"):
        return "step3_thermal"
    
    # 신뢰도가 낮으면 react_agent 호출
    # LLM이 색상 분석을 위해 필요한 도구를 선택
    confidence = step2_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step3_thermal"


def should_use_react_agent_contact_step3(state: InvestigationState) -> Literal["react_agent", "step4_surface"]:
    """
    Contact Expert Step3 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    LLM이 상황을 판단하고 필요한 도구를 선택하게 함
    
    Returns:
        "react_agent": 추가 분석/이미지 편집 필요
        "step4_surface": 다음 Step으로 진행
    """
    step3_result = state.get("contact_step3_result", {})
    
    # 에러가 있으면 다음 Step으로 진행
    if step3_result.get("error"):
        return "step4_surface"
    
    # 신뢰도가 낮으면 react_agent 호출
    # LLM이 열적 구배 분석을 위해 필요한 도구를 선택
    confidence = step3_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step4_surface"


def should_use_react_agent_contact_step4(state: InvestigationState) -> Literal["react_agent", "finalize"]:
    """
    Contact Expert Step4 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    LLM이 상황을 판단하고 필요한 도구를 선택하게 함
    
    Returns:
        "react_agent": 추가 분석/이미지 편집 필요
        "finalize": 최종 정리로 진행
    """
    step4_result = state.get("contact_step4_result", {})
    
    # 에러가 있으면 finalize로 진행
    if step4_result.get("error"):
        return "finalize"
    
    # 신뢰도가 낮으면 react_agent 호출
    # LLM이 표면 분석을 위해 필요한 도구를 선택
    confidence = step4_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "finalize"


# Dielectric Expert 조건부 엣지 함수들
def should_use_react_agent_dielectric_step1(state: InvestigationState) -> Literal["react_agent", "step2_swelling"]:
    """
    Dielectric Expert Step1 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step1_result = state.get("dielectric_step1_result", {})
    
    if step1_result.get("error"):
        return "step2_swelling"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step1_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step2_swelling"


def should_use_react_agent_dielectric_step2(state: InvestigationState) -> Literal["react_agent", "step3_global_aging"]:
    """
    Dielectric Expert Step2 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step2_result = state.get("dielectric_step2_result", {})
    
    if step2_result.get("error"):
        return "step3_global_aging"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step2_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step3_global_aging"


def should_use_react_agent_dielectric_step3(state: InvestigationState) -> Literal["react_agent", "finalize"]:
    """
    Dielectric Expert Step3 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step3_result = state.get("dielectric_step3_result", {})
    
    if step3_result.get("error"):
        return "finalize"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step3_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "finalize"


# Mechanical Expert 조건부 엣지 함수들
def should_use_react_agent_mechanical_step1(state: InvestigationState) -> Literal["react_agent", "step2_splaying"]:
    """
    Mechanical Expert Step1 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step1_result = state.get("mechanical_step1_result", {})
    
    if step1_result.get("error"):
        return "step2_splaying"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step1_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step2_splaying"


def should_use_react_agent_mechanical_step2(state: InvestigationState) -> Literal["react_agent", "step3_confinement"]:
    """
    Mechanical Expert Step2 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step2_result = state.get("mechanical_step2_result", {})
    
    if step2_result.get("error"):
        return "step3_confinement"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step2_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step3_confinement"


def should_use_react_agent_mechanical_step3(state: InvestigationState) -> Literal["react_agent", "finalize"]:
    """
    Mechanical Expert Step3 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step3_result = state.get("mechanical_step3_result", {})
    
    if step3_result.get("error"):
        return "finalize"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step3_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "finalize"


# Tracking Expert 조건부 엣지 함수들
def should_use_react_agent_tracking_step1(state: InvestigationState) -> Literal["react_agent", "step2_luster"]:
    """
    Tracking Expert Step1 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step1_result = state.get("tracking_step1_result", {})
    
    if step1_result.get("error"):
        return "step2_luster"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step1_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step2_luster"


def should_use_react_agent_tracking_step2(state: InvestigationState) -> Literal["react_agent", "step3_erosion"]:
    """
    Tracking Expert Step2 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step2_result = state.get("tracking_step2_result", {})
    
    if step2_result.get("error"):
        return "step3_erosion"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step2_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step3_erosion"


def should_use_react_agent_tracking_step3(state: InvestigationState) -> Literal["react_agent", "finalize"]:
    """
    Tracking Expert Step3 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step3_result = state.get("tracking_step3_result", {})
    
    if step3_result.get("error"):
        return "finalize"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step3_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "finalize"


# StrandFracture Expert 조건부 엣지 함수들
def should_use_react_agent_strand_fracture_step1(state: InvestigationState) -> Literal["react_agent", "step2_bead_distribution"]:
    """
    StrandFracture Expert Step1 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step1_result = state.get("strand_fracture_step1_result", {})
    
    if step1_result.get("error"):
        return "step2_bead_distribution"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step1_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step2_bead_distribution"


def should_use_react_agent_strand_fracture_step2(state: InvestigationState) -> Literal["react_agent", "step3_fatigue"]:
    """
    StrandFracture Expert Step2 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step2_result = state.get("strand_fracture_step2_result", {})
    
    if step2_result.get("error"):
        return "step3_fatigue"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step2_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "step3_fatigue"


def should_use_react_agent_strand_fracture_step3(state: InvestigationState) -> Literal["react_agent", "finalize"]:
    """
    StrandFracture Expert Step3 후 react_agent 호출 여부 결정
    
    Step 결과가 불확실하거나 신뢰도가 낮을 때 react_agent 호출
    """
    step3_result = state.get("strand_fracture_step3_result", {})
    
    if step3_result.get("error"):
        return "finalize"
    
    # 신뢰도가 낮으면 react_agent 호출
    confidence = step3_result.get("confidence", 100)
    
    if confidence < 70:
        return "react_agent"
    
    return "finalize"

