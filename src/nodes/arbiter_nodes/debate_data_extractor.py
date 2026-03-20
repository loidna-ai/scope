"""
논쟁을 위한 데이터 추출 노드
InvestigationState에서 각 전문가의 의견을 구조화하여 추출
"""
from typing import Dict, Any
from src.state import InvestigationState
from src.states.arbiter_debate_state import ExpertOpinion, ExpertName
from src.utils.logging_config import setup_logger
import os

logger = setup_logger(__name__)

def extract_spatial_summary(state: InvestigationState) -> str:
    """Wide Mode: 핫스팟의 공간적 위치 요약 생성"""
    hotspots = state.get("hotspots", [])
    if not hotspots:
        return "공간적 분포(Spatial Context) 정보 없음"
        
    summary_lines = ["\n[다중 지점(Wide Mode) 공간적 분포]"]
    for h in hotspots:
        hid = h.get("id", "Unknown")
        loc = h.get("location_description", "위치 미상")
        srcs = h.get("source_images", [])
        src_str = ", ".join([os.path.basename(s) for s in srcs]) if srcs else "N/A"
        summary_lines.append(f"- Hotspot #{hid}: {loc} (발견 이미지: {src_str})")
        
    return "\n".join(summary_lines)

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
    
    # for expert_name in ["contact", "deform", "necking", "aging"]:
    for expert_name in ["contact", "necking"]:
        expert_data = expert_analysis_results.get(expert_name, {})
        logger.debug(f"Processing {expert_name} expert data")
        
        if not expert_data:
            logger.warning(f"{expert_name} expert data not found, skipping")
            continue
        
        final_result = expert_data.get("final_verdict_result", {})
        
        if not final_result:
            logger.warning(f"{expert_name} expert final_result not found, skipping")
            continue
        
        # 증거 리스트에서 텍스트 추출 (EvidenceItem 구조 지원)
        evidence_data = expert_evidence.get(expert_name)
        evidence_texts = []
        
        items = []
        if hasattr(evidence_data, "evidence_list"):
            items = getattr(evidence_data, "evidence_list", [])
        elif isinstance(evidence_data, dict) and "evidence_list" in evidence_data:
            items = evidence_data["evidence_list"]
        elif isinstance(evidence_data, list):
            items = evidence_data
            
        for ev in items:
            if isinstance(ev, dict):
                fact = ev.get("visual_fact", ev.get("evidence", ""))
            else:
                fact = getattr(ev, "visual_fact", getattr(ev, "evidence", ""))
            
            if fact:
                evidence_texts.append(fact)
        
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
    논쟁 상태 초기화 (debate_init)
    
    expert_opinions, expert_reports 등은 wrapper에서 이미 주입됨.
    논쟁 진행 상태(debate_messages, current_stage, round 등)만 초기화.
    
    Args:
        state: ArbiterDebateState (wrapper에서 expert_* 필드 설정됨)
        
    Returns:
        논쟁 진행 상태 초기값
    """
    logger.info("Debate init: opening stage, round 1")
    
    # 이미 래퍼 노드에서 expert_opinions 등이 설정되어 있으므로
    # 논쟁 진행 상태만 초기화
    return {
        "debate_messages": [],
        "current_stage": "opening",
        "current_round": 1,
        "current_speaker": None,
        "fact_check_failures": {"contact": 0, "necking": 0}, # "deform": 0, "aging": 0
        "final_verdict": None,
        "consensus_reached": False,
        "errors": []
    }
