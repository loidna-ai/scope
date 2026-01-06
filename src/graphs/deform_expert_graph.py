"""
Deform (압착/손상) 전문가 서브그래프 빌더
(Updated for Multi-Hotspot & Wire/Plug Classification)
"""
from typing import Dict, Any, Optional, Literal
import os

from langgraph.graph import StateGraph, START, END

from src.state import InvestigationState
from src.nodes.deform_nodes import (
    DeformExpertState,
    hotspot_detector_node,
    hotspot_manager_node,
    roi_crop_node,
    component_classifier_node,
    deform_wire_node,
    deform_plug_node,
    result_aggregator_node,
    verdict_node
)
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file

def route_loop_manager(state: DeformExpertState) -> Literal["process", "end"]:
    """Hotspot Manager 분기"""
    if state.get("current_hotspot"):
        return "process"
    return "end"

def route_component_type(state: DeformExpertState) -> Literal["wire", "plug", "none"]:
    """Component Type에 따른 Specialist 분기"""
    conn_type = state.get("connection_type", "None")
    
    # 1. Wire -> Deform Wire Analysis (Compression/Cut)
    if "Wire" in conn_type or "전선" in conn_type:
        return "wire"
        
    # 2. Plug -> Deform Plug Analysis (Crushing)
    if any(k in conn_type for k in ["Plug", "플러그", "Terminal", "터미널"]):
        return "plug"
        
    return "none"

def build_deform_expert_graph():
    """Deform 전문가 서브그래프 빌드"""
    builder = StateGraph(DeformExpertState)
    
    builder.add_node("hotspot_detector", hotspot_detector_node)
    builder.add_node("hotspot_manager", hotspot_manager_node)
    builder.add_node("roi_crop", roi_crop_node)
    builder.add_node("component_classifier", component_classifier_node)
    
    # Specialists
    builder.add_node("deform_wire", deform_wire_node)
    builder.add_node("deform_plug", deform_plug_node)
    
    builder.add_node("result_aggregator", result_aggregator_node)
    builder.add_node("verdict", verdict_node)
    
    # Edges
    builder.add_edge(START, "hotspot_detector")
    builder.add_edge("hotspot_detector", "hotspot_manager")
    
    builder.add_conditional_edges(
        "hotspot_manager",
        route_loop_manager,
        {"process": "roi_crop", "end": "verdict"}
    )
    
    builder.add_edge("roi_crop", "component_classifier")
    
    builder.add_conditional_edges(
        "component_classifier",
        route_component_type,
        {
            "wire": "deform_wire",
            "plug": "deform_plug",
            "none": "result_aggregator"
        }
    )
    
    builder.add_edge("deform_wire", "result_aggregator")
    builder.add_edge("deform_plug", "result_aggregator")
    builder.add_edge("result_aggregator", "hotspot_manager")
    
    builder.add_edge("verdict", END)
    
    return builder.compile()

def _cleanup_temp_files(temp_image_path: Optional[str], final_state: Optional[Dict[str, Any]]):
    if temp_image_path and os.path.exists(temp_image_path):
        try:
            os.remove(temp_image_path)
        except Exception:
            pass
    if final_state:
        # Loop에서 생성된 ROI 파일들 정리 (Best Effort)
        roi_path = final_state.get("roi_image_path")
        if roi_path and os.path.exists(roi_path) and roi_path != temp_image_path:
             try:
                os.remove(roi_path)
             except Exception:
                pass

def deform_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    import traceback
    temp_image_path = None
    final_state = None
    try:
        image_data = extract_image_from_payload(state.get("payload", []))
        if image_data is None:
            return {
                "errors": ["Deform 전문가: 이미지를 추출할 수 없습니다."],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
            
        temp_image_path = save_bytes_to_temp_file(image_data)
        
        initial_state: DeformExpertState = {
            "messages": [],
            "image_path": temp_image_path,
            "hotspots": [],
            "hotspot_queue": None,
            "analysis_results": [],
            "current_hotspot": None,
            "detector_result": None,
            "roi_image_path": None,
            "connection_type": None,
            "specialist_result": None,
            "verdict_report": None,
            "verdict_confidence": None,
            "verdict_result": None
        }
        
        graph = build_deform_expert_graph()
        final_state = graph.invoke(initial_state, config={"recursion_limit": 50})
        
        verdict_report = final_state.get("verdict_report", "")
        verdict_confidence = final_state.get("verdict_confidence", 0)
        verdict_result = final_state.get("verdict_result", {})
        analysis_results = final_state.get("analysis_results", [])
        
        evidence = []
        if verdict_result:
            visual_desc = verdict_result.get("visual_observation", "")
            verdict = verdict_result.get("verdict", "")
            if verdict:
                evidence.append({
                    "evidence": verdict,
                    "details": visual_desc
                })
        
        return {
            "expert_reports": [verdict_report] if verdict_report else ["분석 결과 없음"],
            "expert_analysis_results": {
                "deform": {
                    "multi_hotspot_results": analysis_results,
                    "final_verdict_result": verdict_result
                }
            },
            "expert_confidence_scores": {"deform": verdict_confidence},
            "expert_evidence": {"deform": evidence}
        }
        
    except Exception as e:
        print(f"\n[ERROR] Deform Expert Wrapper Exception: {str(e)}")
        traceback.print_exc()
        return {
            "errors": [f"Deform 전문가 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }
    finally:
        _cleanup_temp_files(temp_image_path, final_state)
