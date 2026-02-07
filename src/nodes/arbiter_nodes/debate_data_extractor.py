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
    
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(__file__).parent.parent.parent.parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"debate_data_extractor.py:9","message":"extract_expert_opinions entry","data":{"expert_analysis_results_keys":list(expert_analysis_results.keys())},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
    expert_opinions: Dict[ExpertName, ExpertOpinion] = {}
    expert_confidence_scores = state.get("expert_confidence_scores", {})
    expert_evidence = state.get("expert_evidence", {})
    
    for expert_name in ["contact", "deform", "necking"]:
        expert_data = expert_analysis_results.get(expert_name, {})
        logger.debug(f"Processing {expert_name} expert data")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"debate_data_extractor.py:25","message":"processing expert","data":{"expert_name":expert_name,"has_expert_data":bool(expert_data)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        if not expert_data:
            logger.warning(f"{expert_name} expert data not found, skipping")
            continue
        
        final_result = expert_data.get("final_verdict_result", {})
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"debate_data_extractor.py:33","message":"checking final_result","data":{"expert_name":expert_name,"has_final_result":bool(final_result)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        if not final_result:
            logger.warning(f"{expert_name} expert final_result not found, skipping")
            continue
        
        # 증거 리스트에서 텍스트 추출 (details 필드도 활용)
        evidence_list = expert_evidence.get(expert_name, [])
        evidence_texts = []
        for ev in evidence_list:
            evidence_text = ev.get("evidence", "")
            details = ev.get("details", "")
            if evidence_text:
                if details:
                    evidence_texts.append(f"{evidence_text}\n상세: {details}")
                else:
                    evidence_texts.append(evidence_text)
        
        # reasoning 필드 사용 (없으면 verdict를 fallback으로 사용)
        reasoning_text = final_result.get("reasoning", "")
        if not reasoning_text:
            reasoning_text = final_result.get("verdict", "")  # Fallback
        
        expert_opinions[expert_name] = {
            "conclusion": final_result.get("conclusion", ""),
            "confidence": expert_confidence_scores.get(expert_name, 0),
            "verdict": final_result.get("verdict", ""),
            "visual_description": final_result.get("visual_description", ""),
            "evidence": evidence_texts,
            "reasoning": reasoning_text  # 실제 reasoning 필드 사용
        }
        
        logger.info(f"{expert_name} expert opinion extracted (confidence: {expert_confidence_scores.get(expert_name, 0)}%)")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"debate_data_extractor.py:47","message":"expert opinion created","data":{"expert_name":expert_name,"has_conclusion":bool(expert_opinions[expert_name].get("conclusion"))},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
    
    logger.info(f"Expert opinions extraction completed: {len(expert_opinions)} opinions extracted")
    
    # #region agent log
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"debate_data_extractor.py:52","message":"extract_expert_opinions exit","data":{"expert_opinions_count":len(expert_opinions),"expert_opinions_keys":list(expert_opinions.keys())},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
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
        "fact_check_failures": {"contact": 0, "deform": 0, "necking": 0},
        "final_verdict": None,
        "consensus_reached": False,
        "errors": []
    }
