"""
Tracking 전문가 서브그래프 빌더 (Multi-Hotspot Loop)
"""
import os
import time
import traceback
from typing import Dict, Any, Optional, Literal

from langgraph.graph import StateGraph, START, END

from src.state import InvestigationState
from src.nodes.tracking_nodes import (
    TrackingExpertState,
    hotspot_detector_node,
    hotspot_manager_node,
    roi_crop_node,
    component_classifier_node,
    tracking_terminal_node,
    tracking_plug_node,
    tracking_pcb_node,
    result_aggregator_node,
    verdict_node
)
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file

def route_loop_manager(state: TrackingExpertState) -> Literal["process", "end"]:
    """처리할 Hotspot이 남아있는지 확인"""
    if state.get("current_hotspot"):
        return "process"
    return "end"

def route_component_type(state: TrackingExpertState) -> Literal["terminal", "plug", "pcb", "none"]:
    """Component Classification 분기"""
    conn_type = state.get("connection_type", "None")
    
    # Loose Matching & Multilingual Support
    if "Terminal" in conn_type or "단자" in conn_type:
        return "terminal"
    elif "Plug" in conn_type or "플러그" in conn_type:
        return "plug"
    elif "PCB" in conn_type or "기판" in conn_type:
        return "pcb"
    
    return "none"

def build_tracking_expert_graph():
    """Tracking 전문가 서브그래프 빌드 - Multi-Hotspot Loop"""
    builder = StateGraph(TrackingExpertState)
    
    # 노드 추가
    builder.add_node("hotspot_detector", hotspot_detector_node)
    builder.add_node("hotspot_manager", hotspot_manager_node)
    builder.add_node("roi_crop", roi_crop_node)
    builder.add_node("component_classifier", component_classifier_node)
    
    builder.add_node("tracking_terminal", tracking_terminal_node)
    builder.add_node("tracking_plug", tracking_plug_node)
    builder.add_node("tracking_pcb", tracking_pcb_node)
    
    builder.add_node("result_aggregator", result_aggregator_node)
    builder.add_node("verdict", verdict_node)
    
    # 엣지 연결
    # 1. Start -> Detector -> Manager
    builder.add_edge(START, "hotspot_detector")
    builder.add_edge("hotspot_detector", "hotspot_manager")
    
    # 2. Manager Loop Control
    builder.add_conditional_edges(
        "hotspot_manager",
        route_loop_manager,
        {
            "process": "roi_crop",
            "end": "verdict"
        }
    )
    
    # 3. Pipeline: Crop -> Classifier (Branching)
    builder.add_edge("roi_crop", "component_classifier")
    
    builder.add_conditional_edges(
        "component_classifier",
        route_component_type,
        {
            "terminal": "tracking_terminal",
            "plug": "tracking_plug",
            "pcb": "tracking_pcb",
            "none": "result_aggregator"
        }
    )
    
    # 4. Specialist -> Aggregator
    builder.add_edge("tracking_terminal", "result_aggregator")
    builder.add_edge("tracking_plug", "result_aggregator")
    builder.add_edge("tracking_pcb", "result_aggregator")
    
    # 5. Aggregator -> Manager (Loop Back)
    builder.add_edge("result_aggregator", "hotspot_manager")
    
    # 6. Verdict -> End
    builder.add_edge("verdict", END)
    
    return builder.compile()

def _cleanup_temp_files(temp_image_path: Optional[str], final_state: Optional[Dict[str, Any]]):
    """임시 파일 정리"""
    try:
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
            
        if final_state:
            roi_path = final_state.get("roi_image_path")
            if roi_path and os.path.exists(roi_path) and roi_path != temp_image_path:
                os.remove(roi_path)
    except Exception:
        pass

def tracking_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    """InvestigationState와 전문가 서브그래프를 연결하는 래퍼 노드"""
    temp_image_path = None
    final_state = None
    
    try:
        # 1. 이미지 추출
        image_data = extract_image_from_payload(state.get("payload", []))
        if image_data is None:
            return {
                "errors": ["Tracking 전문가: 이미지를 추출할 수 없습니다."],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        # 2. 임시 파일 저장
        temp_image_path = save_bytes_to_temp_file(image_data)
        
        # 3. 초기 상태 설정
        initial_state: TrackingExpertState = {
            "messages": [],
            "image_path": temp_image_path,
            "hotspots": [],
            "hotspot_queue": None,
            "analysis_results": [],
            "current_hotspot": None,
            "detector_result": None,
            "roi_image_path": None,
            "connection_type": None,
            "tracking_terminal_result": None,
            "tracking_plug_result": None,
            "tracking_pcb_result": None,
            "verdict_report": None,
            "verdict_confidence": None,
            "verdict_result": None
        }
        
        # 4. 그래프 실행
        graph = build_tracking_expert_graph()
        final_state = graph.invoke(initial_state, config={"recursion_limit": 50})
        
        # 5. 결과 추출
        verdict_report = final_state.get("verdict_report", "")
        verdict_confidence = final_state.get("verdict_confidence", 0)
        verdict_result = final_state.get("verdict_result", {})
        analysis_results = final_state.get("analysis_results", [])
        
        # 6. 증거 변환 (새 형식에 맞춤)
        evidence = []
        if verdict_result:
             visual_desc = verdict_result.get("visual_description", "")
             reasoning = verdict_result.get("reasoning", "")
             if visual_desc or reasoning:
                 # Contact Expert style matches: evidence field name can be flexible but "Tracking Signs" is a good generic header if specific feature name isn't available easily
                 # Actually in verdict_node of tracking, it selects 'best_entry'. 
                 evidence.append({
                     "evidence": "Tracking Signs", # This could be refined if verdict_result has 'feature_name'
                     "details": f"{visual_desc}\n\nReasoning: {reasoning}"
                 })
        
        return {
            "expert_reports": [verdict_report] if verdict_report else ["분석 결과 없음"],
            "expert_analysis_results": {
                "tracking": {
                    "multi_hotspot_results": analysis_results,
                    "final_verdict_result": verdict_result
                }
            },
            "expert_confidence_scores": {"tracking": verdict_confidence},
            "expert_evidence": {"tracking": evidence}
        }
        
    except Exception as e:
        traceback.print_exc()
        return {
            "errors": [f"Tracking 전문가 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }
    finally:
        _cleanup_temp_files(temp_image_path, final_state)
