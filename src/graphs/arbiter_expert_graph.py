"""
Arbiter Expert 서브그래프 빌더
Deb8flow 스타일의 논쟁 시스템을 서브그래프로 구현
"""
import traceback
from typing import Dict, Any, Optional, Literal

from langgraph.graph import StateGraph, START, END

from src.state import InvestigationState
from src.states.arbiter_debate_state import ArbiterDebateState, ExpertName
from src.nodes.arbiter_nodes.debate_data_extractor import debate_data_extractor_node, extract_expert_opinions
from src.nodes.arbiter_nodes.expert_debater_nodes import (
    contact_debater_node,
    deform_debater_node,
    necking_debater_node,
    aging_debater_node
)
from src.nodes.arbiter_nodes.fact_checker_node import fact_checker_node
from src.nodes.arbiter_nodes.fact_check_router_node import fact_check_router_node
from src.nodes.arbiter_nodes.debate_moderator_node import debate_moderator_node
from src.nodes.arbiter_nodes.judge_node import judge_node

from src.utils.logging_config import setup_logger
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file

logger = setup_logger(__name__)

# ===== Graph Builder =====

def build_arbiter_expert_graph():
    """
    Arbiter Expert 서브그래프 빌드
    
    워크플로우 (Option C: 조건부 2단계):
    START → debate_init → 합의 체크
         → [합의] → judge (Debate 스킵)
         → [불일치] → debater → fact_checker → ... → judge
    """
    builder = StateGraph(ArbiterDebateState)
    
    # 노드 추가 (debate_init: 논쟁 상태 초기화, expert_opinions는 wrapper에서 주입)
    builder.add_node("debate_init", debate_data_extractor_node)
    builder.add_node("contact_debater", contact_debater_node)
    # builder.add_node("deform_debater", deform_debater_node)
    builder.add_node("necking_debater", necking_debater_node)
    # builder.add_node("aging_debater", aging_debater_node)
    builder.add_node("fact_checker", fact_checker_node)
    # fact_check_router는 노드가 아니라 라우팅 함수로만 사용
    builder.add_node("moderator", debate_moderator_node)
    builder.add_node("judge", judge_node)
    
    # 엣지 추가
    builder.add_edge(START, "debate_init")
    
    # [Option C] 초기화 후 전문가 간 합의 여부에 따라 조건부 라우팅
    # - 합의 시: judge 직접 호출 (Debate 스킵)
    # - 불일치 시: 기존 Debate 흐름 시작
    builder.add_conditional_edges(
        "debate_init",
        route_after_extraction,
        {
            "contact_debater": "contact_debater",
            # "deform_debater": "deform_debater",
            "necking_debater": "necking_debater",
            # "aging_debater": "aging_debater",
            "judge": "judge"
        }
    )
    
    # 모든 Debater → Fact Checker
    builder.add_edge("contact_debater", "fact_checker")
    # builder.add_edge("deform_debater", "fact_checker")
    builder.add_edge("necking_debater", "fact_checker")
    # builder.add_edge("aging_debater", "fact_checker")
    
    # Fact Checker → Router (조건부 라우팅)
    builder.add_conditional_edges(
        "fact_checker",
        fact_check_router_node,  # 라우팅 함수 직접 사용
        {
            "contact_debater": "contact_debater",
            # "deform_debater": "deform_debater",
            "necking_debater": "necking_debater",
            # "aging_debater": "aging_debater",
            "moderator": "moderator",
            "judge": "judge"
        }
    )
    
    # Moderator → Debater (다음 라운드) OR Judge
    builder.add_conditional_edges(
        "moderator",
        route_from_moderator,
        {
            "contact_debater": "contact_debater",
            # "deform_debater": "deform_debater",
            "necking_debater": "necking_debater",
            # "aging_debater": "aging_debater",
            "judge": "judge"
        }
    )
    
    # Judge → END
    builder.add_edge("judge", END)
    
    return builder.compile()

def route_after_extraction(state: ArbiterDebateState) -> str:
    """
    [Option C] 전문가 간 결론 비교 후 Debate 필요 여부 결정
    
    - 전문가 1명 이하: debate 불필요 → judge 직접
    - 전원 합의 (전부 양성 또는 전부 음성): judge 직접 (Debate 스킵)
    - 불일치 (양성/음성 혼합): debate 시작
    """
    opinions = state.get("expert_opinions", {})
    
    if len(opinions) < 2:
        logger.info(f"Arbiter: Only {len(opinions)} expert(s) present, skipping debate → judge")
        return "judge"
    
    # 결론 추출
    conclusions = {name: op.get("conclusion", "") for name, op in opinions.items()}
    
    # 양성 계열 키워드 (유력/의심 판정)
    POSITIVE_KEYWORDS = ["유력", "의심", "접촉불량", "압착", "손상", "반단선"]
    
    positive_experts = []
    negative_experts = []
    for name, conclusion in conclusions.items():
        if any(kw in conclusion for kw in POSITIVE_KEYWORDS):
            positive_experts.append(name)
        else:
            negative_experts.append(name)
    
    # 전원 합의 체크 (전부 양성 또는 전부 음성)
    if len(positive_experts) == 0 or len(negative_experts) == 0:
        logger.info(
            f"Arbiter: Expert consensus detected → judge (skip debate)\n"
            f"  Conclusions: {conclusions}\n"
            f"  Positive: {positive_experts}, Negative: {negative_experts}"
        )
        return "judge"
    
    # 불일치 → debate 시작
    logger.info(
        f"Arbiter: Expert disagreement detected → starting debate\n"
        f"  Conclusions: {conclusions}\n"
        f"  Positive: {positive_experts}, Negative: {negative_experts}"
    )
    return route_to_first_debater(state)

def route_to_first_debater(state: ArbiterDebateState) -> str:
    """데이터 추출 후 가장 신뢰도가 높은 전문가를 첫 발언자로 라우팅"""
    VALID_DEBATERS = {"contact", "necking"} # "deform", "aging" 제거
    scores = state.get("expert_confidence_scores", {})
    
    if scores:
        # 유효한 전문가 중 최고 신뢰도 선택
        valid_scores = {k: v for k, v in scores.items() if k in VALID_DEBATERS}
        if valid_scores:
            best = max(valid_scores, key=valid_scores.get)
            logger.info(f"Arbiter: First debater selected by confidence: {best} (score={valid_scores[best]})")
            return f"{best}_debater"
    
    # Fallback: 점수 없으면 Contact부터 시작
    logger.info("Arbiter: No confidence scores available, defaulting to contact_debater")
    return "contact_debater"

def route_from_moderator(state: ArbiterDebateState) -> str:
    """Moderator에서 다음 노드로 라우팅"""
    stage = state.get("current_stage", "opening")
    next_speaker = state.get("current_speaker")
    
    if stage == "judgment":
        return "judge"
    
    if next_speaker:
        return f"{next_speaker}_debater"
    
    # Fallback: 합의 도달 또는 최종 라운드 완료
    if state.get("consensus_reached", False):
        return "judge"
    
    # 기본적으로 다음 발언자로
    return "contact_debater"

# ===== Wrapper Node =====

async def arbiter_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    logger.info("Arbiter Expert wrapper: Starting debate process")
    
    try:
        # InvestigationState에서 데이터 추출
        expert_analysis_results = state.get("expert_analysis_results", {})
        expert_confidence_scores = state.get("expert_confidence_scores", {})
        expert_evidence = state.get("expert_evidence", {})
        expert_reports = state.get("expert_reports", [])
        
        logger.debug(f"Arbiter wrapper: Extracting data from {len(expert_reports)} expert reports")
        
        if not expert_reports:
            logger.error("Arbiter wrapper: No expert reports found")
            return {
                "errors": ["Arbiter 전문가: 전문가 리포트가 없습니다."],
                "final_verdict": None,
                "arbiter_debate_messages": []  # 빈 리스트로 초기화
            }
        
        # 각 전문가의 의견 추출
        expert_opinions = extract_expert_opinions(state)
        
        logger.info(f"Arbiter wrapper: Extracted {len(expert_opinions)} expert opinions")
        
        if not expert_opinions:
            logger.info("Arbiter wrapper: No expert opinions (Contact/Necking 모두 스킵) → UNDETERMINED")
            verdict = """**최종 판정**: UNDETERMINED (분석 대상 없음)
**신뢰도**: 0.0% (Low)

**판정 근거:**
분석할 접속부 또는 반단선 증거가 없습니다. 모든 Hotspot이 해당 전문가의 분석 대상이 아니었습니다."""
            return {
                "errors": [],
                "final_verdict": verdict,
                "final_verdict_structured": None,
                "arbiter_debate_messages": [{
                    "speaker": "judge",
                    "content": verdict,
                    "validated": True,
                    "stage": "judgment",
                    "round_num": 1
                }]
            }
        
        # ArbiterDebateState로 변환
        initial_state: ArbiterDebateState = {
            "expert_opinions": expert_opinions,
            "expert_reports": expert_reports,
            "expert_confidence_scores": expert_confidence_scores,
            "expert_evidence": expert_evidence,
            "debate_messages": [],
            "current_stage": "opening",
            "current_round": 1,
            "current_speaker": None,
            "fact_check_failures": {"contact": 0, "necking": 0}, # "deform": 0, "aging": 0
            "final_verdict": None,
            "final_verdict_structured": None,  # 구조화된 데이터 초기화
            "consensus_reached": False,
            "errors": []
        }
        
        # 서브그래프 실행
        logger.info("Arbiter wrapper: Building debate graph")
        
        graph = build_arbiter_expert_graph()
        
        logger.info("Arbiter wrapper: Invoking debate graph")
        
        final_state = await graph.ainvoke(initial_state, config={"recursion_limit": 50})
        
        has_verdict = bool(final_state.get("final_verdict"))
        logger.info(f"Arbiter wrapper: Debate graph completed (verdict: {'generated' if has_verdict else 'not generated'})")
        
        # InvestigationState로 변환하여 반환
        debate_messages = final_state.get("debate_messages", [])
        logger.info(f"Arbiter wrapper: Debate completed with {len(debate_messages)} messages")
        
        result = {
            "final_verdict": final_state.get("final_verdict"),
            "final_verdict_structured": final_state.get("final_verdict_structured"),  # 구조화된 데이터 전달
            "arbiter_debate_messages": debate_messages,
            "errors": final_state.get("errors", [])
        }
        
        if result.get("errors"):
            logger.warning(f"Arbiter wrapper: {len(result['errors'])} errors occurred")
        
        return result
    
    except Exception as e:
        logger.error(f"Arbiter Expert Wrapper Exception: {e}", exc_info=True)
        traceback.print_exc()
        return {
            "errors": [f"Arbiter 전문가 오류: {str(e)}"],
            "final_verdict": None,
            "arbiter_debate_messages": []  # 빈 리스트로 초기화
        }
