"""
Arbiter Expert 서브그래프 빌더
Deb8flow 스타일의 논쟁 시스템을 서브그래프로 구현
"""
import os
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, Literal

from langgraph.graph import StateGraph, START, END

from src.state import InvestigationState
from src.states.arbiter_debate_state import ArbiterDebateState, ExpertName
from src.nodes.arbiter_nodes.debate_data_extractor import debate_data_extractor_node, extract_expert_opinions
from src.nodes.arbiter_nodes.expert_debater_nodes import (
    contact_debater_node_sync,
    deform_debater_node_sync,
    necking_debater_node_sync
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
    
    워크플로우:
    START → data_extractor → (contact/deform/necking)_debater → fact_checker 
         → fact_check_router → (retry OR moderator) → (다음 라운드 OR judge) → END
    """
    builder = StateGraph(ArbiterDebateState)
    
    # 노드 추가
    builder.add_node("data_extractor", debate_data_extractor_node)
    builder.add_node("contact_debater", contact_debater_node_sync)
    builder.add_node("deform_debater", deform_debater_node_sync)
    builder.add_node("necking_debater", necking_debater_node_sync)
    builder.add_node("fact_checker", fact_checker_node)
    # fact_check_router는 노드가 아니라 라우팅 함수로만 사용
    builder.add_node("moderator", debate_moderator_node)
    builder.add_node("judge", judge_node)
    
    # 엣지 추가
    builder.add_edge(START, "data_extractor")
    
    # 데이터 추출 후 첫 번째 발언자로 라우팅
    builder.add_conditional_edges(
        "data_extractor",
        route_to_first_debater,
        {
            "contact_debater": "contact_debater",
            "deform_debater": "deform_debater",
            "necking_debater": "necking_debater"
        }
    )
    
    # 모든 Debater → Fact Checker
    builder.add_edge("contact_debater", "fact_checker")
    builder.add_edge("deform_debater", "fact_checker")
    builder.add_edge("necking_debater", "fact_checker")
    
    # Fact Checker → Router (조건부 라우팅)
    builder.add_conditional_edges(
        "fact_checker",
        fact_check_router_node,  # 라우팅 함수 직접 사용
        {
            "contact_debater": "contact_debater",
            "deform_debater": "deform_debater",
            "necking_debater": "necking_debater",
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
            "deform_debater": "deform_debater",
            "necking_debater": "necking_debater",
            "judge": "judge"
        }
    )
    
    # Judge → END
    builder.add_edge("judge", END)
    
    return builder.compile()

def route_to_first_debater(state: ArbiterDebateState) -> Literal["contact_debater", "deform_debater", "necking_debater"]:
    """데이터 추출 후 첫 번째 발언자로 라우팅"""
    # 첫 번째는 Contact부터 시작
    return "contact_debater"

def route_from_moderator(state: ArbiterDebateState) -> Literal["contact_debater", "deform_debater", "necking_debater", "judge"]:
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

def arbiter_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    """
    Arbiter Expert wrapper node for main investigation graph
    
    InvestigationState를 ArbiterDebateState로 변환하여 서브그래프 실행
    """
    logger.info("Arbiter Expert wrapper: Starting debate process")
    
    # #region agent log
    import json
    import time
    log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"arbiter_expert_graph.py:126","message":"arbiter_expert_wrapper_node entry","data":{"state_keys":list(state.keys()) if state else None,"has_expert_reports":bool(state.get("expert_reports"))},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
    
    try:
        # InvestigationState에서 데이터 추출
        expert_analysis_results = state.get("expert_analysis_results", {})
        expert_confidence_scores = state.get("expert_confidence_scores", {})
        expert_evidence = state.get("expert_evidence", {})
        expert_reports = state.get("expert_reports", [])
        
        logger.debug(f"Arbiter wrapper: Extracting data from {len(expert_reports)} expert reports")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"arbiter_expert_graph.py:140","message":"data extraction","data":{"expert_reports_count":len(expert_reports),"expert_analysis_results_keys":list(expert_analysis_results.keys()),"expert_confidence_scores_keys":list(expert_confidence_scores.keys())},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        if not expert_reports:
            logger.error("Arbiter wrapper: No expert reports found")
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"arbiter_expert_graph.py:145","message":"no expert reports","data":{},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            return {
                "errors": ["Arbiter 전문가: 전문가 리포트가 없습니다."],
                "final_verdict": None
            }
        
        # 각 전문가의 의견 추출
        expert_opinions = extract_expert_opinions(state)
        
        logger.info(f"Arbiter wrapper: Extracted {len(expert_opinions)} expert opinions")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"arbiter_expert_graph.py:152","message":"expert_opinions extracted","data":{"expert_opinions_keys":list(expert_opinions.keys()),"expert_opinions_count":len(expert_opinions)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        if not expert_opinions:
            logger.error("Arbiter wrapper: No expert opinions extracted")
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"arbiter_expert_graph.py:157","message":"no expert opinions","data":{},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            return {
                "errors": ["Arbiter 전문가: 전문가 의견 데이터가 없습니다."],
                "final_verdict": None
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
            "fact_check_failures": {"contact": 0, "deform": 0, "necking": 0},
            "final_verdict": None,
            "consensus_reached": False,
            "errors": []
        }
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"arbiter_expert_graph.py:175","message":"initial_state created","data":{"initial_state_keys":list(initial_state.keys())},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # 서브그래프 실행
        logger.info("Arbiter wrapper: Building debate graph")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"arbiter_expert_graph.py:180","message":"building graph","data":{},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        graph = build_arbiter_expert_graph()
        
        logger.info("Arbiter wrapper: Invoking debate graph")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"arbiter_expert_graph.py:185","message":"invoking graph","data":{"recursion_limit":50},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        final_state = graph.invoke(initial_state, config={"recursion_limit": 50})
        
        has_verdict = bool(final_state.get("final_verdict"))
        logger.info(f"Arbiter wrapper: Debate graph completed (verdict: {'generated' if has_verdict else 'not generated'})")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"arbiter_expert_graph.py:189","message":"graph invoke completed","data":{"final_state_keys":list(final_state.keys()) if final_state else None,"has_final_verdict":has_verdict},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # InvestigationState로 변환하여 반환
        debate_messages = final_state.get("debate_messages", [])
        logger.info(f"Arbiter wrapper: Debate completed with {len(debate_messages)} messages")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"arbiter_expert_graph.py:255","message":"Extracting debate_messages","data":{"debate_messages_count":len(debate_messages),"debate_messages_type":type(debate_messages).__name__,"final_state_has_debate_messages":"debate_messages" in final_state if final_state else False},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        result = {
            "final_verdict": final_state.get("final_verdict"),
            "arbiter_debate_messages": debate_messages,
            "errors": final_state.get("errors", [])
        }
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"arbiter_expert_graph.py:262","message":"Result prepared","data":{"result_keys":list(result.keys()),"arbiter_debate_messages_count":len(result.get("arbiter_debate_messages", [])),"arbiter_debate_messages_is_none":result.get("arbiter_debate_messages") is None},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        if result.get("errors"):
            logger.warning(f"Arbiter wrapper: {len(result['errors'])} errors occurred")
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"arbiter_expert_graph.py:199","message":"arbiter_expert_wrapper_node exit","data":{"result_keys":list(result.keys()),"has_final_verdict":has_verdict,"debate_messages_in_result":len(result.get("arbiter_debate_messages", []))},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        return result
    
    except Exception as e:
        logger.error(f"Arbiter Expert Wrapper Exception: {e}", exc_info=True)
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"arbiter_expert_graph.py:205","message":"exception caught","data":{"error_type":type(e).__name__,"error_message":str(e)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        traceback.print_exc()
        return {
            "errors": [f"Arbiter 전문가 오류: {str(e)}"],
            "final_verdict": None
        }
