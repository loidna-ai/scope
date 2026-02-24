"""
논쟁을 위한 데이터 추출 노드
InvestigationState에서 각 전문가의 의견을 구조화하여 추출
"""
from typing import Dict, Any
from src.state import InvestigationState
from src.states.arbiter_debate_state import ExpertOpinion, ExpertName
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)

def extract_expert_opinions(state: InvestigationState) -> Dict[ExpertName, ExpertOpinion]:
    """
    각 전문가의 의견을 구조화하여 추출
    
    Args:
        state: InvestigationState
        
    Returns:
        전문가별 구조화된 의견 딕셔너리
    """
    expert_analysis_results = state.get("expert_analysis_results", {})
    logger.info(f"Extracting expert opinions from {len(expert_analysis_results)} experts")
    
    expert_opinions: Dict[ExpertName, ExpertOpinion] = {}
    expert_confidence_scores = state.get("expert_confidence_scores", {})
    expert_evidence = state.get("expert_evidence", {})
    
    for expert_name in ["contact", "deform", "necking", "aging"]:
        expert_data = expert_analysis_results.get(expert_name, {})
        logger.debug(f"Processing {expert_name} expert data")
        
        if not expert_data:
            logger.warning(f"{expert_name} expert data not found, skipping")
            continue
        
        final_result = expert_data.get("final_verdict_result", {})
        
        if not final_result:
            logger.warning(f"{expert_name} expert final_result not found, skipping")
            continue
        
        # 증거 리스트에서 텍스트 추출 (details 필드도 활용)
        evidence_list = expert_evidence.get(expert_name, [])
        evidence_texts = []
        for ev in evidence_list:
            evidence_texts.append(ev.get("evidence", ""))
        
        # reasoning 필드 사용 (없으면 verdict를 fallback으로 사용)
        reasoning_text = final_result.get("reasoning", "")
        if not reasoning_text:
            reasoning_text = final_result.get("verdict", "")  # Fallback

        # verdict_result는 "verdict" 키에 결론을 저장 (verdict_finalize_node)
        # "conclusion"은 호환성을 위해 verdict를 fallback으로 사용
        conclusion_text = final_result.get("conclusion", final_result.get("verdict", ""))

        expert_opinions[expert_name] = {
            "conclusion": conclusion_text,
            "confidence": expert_confidence_scores.get(expert_name, 0),
            "verdict": final_result.get("verdict", ""),
            "visual_description": final_result.get("visual_description", ""),
            "evidence": evidence_texts,
            "reasoning": reasoning_text  # 실제 reasoning 필드 사용
        }
        
        logger.info(f"{expert_name} expert opinion extracted (confidence: {expert_confidence_scores.get(expert_name, 0)}%)")
    
    logger.info(f"Expert opinions extraction completed: {len(expert_opinions)} opinions extracted")
    
    return expert_opinions

def debate_data_extractor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    논쟁을 위한 데이터 추출 및 초기 상태 설정
    
    이 노드는 서브그래프 내부에서 사용되며,
    래퍼 노드에서 이미 추출된 데이터를 받아 초기화합니다.
    
    Args:
        state: ArbiterDebateState (일부 필드만 설정된 상태)
        
    Returns:
        초기화된 ArbiterDebateState
    """
    logger.info("Initializing debate state: opening stage, round 1")
    
    # 이미 래퍼 노드에서 expert_opinions 등이 설정되어 있으므로
    # 논쟁 진행 상태만 초기화
    return {
        "debate_messages": [],
        "current_stage": "opening",
        "current_round": 1,
        "current_speaker": None,
        "fact_check_failures": {"contact": 0, "deform": 0, "necking": 0, "aging": 0},
        "final_verdict": None,
        "consensus_reached": False,
        "errors": []
    }
