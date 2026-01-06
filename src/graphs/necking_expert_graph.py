"""
Necking 전문가 서브그래프 빌더
"""
from typing import Dict, Any, Optional, Literal, List
import os

from langgraph.graph import StateGraph, START, END

from src.state import InvestigationState
from src.nodes.necking_nodes import (
    NeckingExpertState,
    hotspot_detector_node,
    hotspot_manager_node,
    roi_crop_node,
    component_classifier_node,
    necking_wire_node,
    result_aggregator_node,
    verdict_node
)
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file

def route_loop_manager(state: NeckingExpertState) -> Literal["process", "end"]:
    """
    Hotspot Manager 분기: 처리할 Hotspot이 있으면 process, 없으면 end
    """
    if state.get("current_hotspot"):
        return "process"
    return "end"

def build_necking_expert_graph():
    """Necking 전문가 서브그래프 빌드 - Multi-Hotspot Loop"""
    builder = StateGraph(NeckingExpertState)
    
    # 노드 추가
    builder.add_node("hotspot_detector", hotspot_detector_node)
    builder.add_node("hotspot_manager", hotspot_manager_node)
    builder.add_node("roi_crop", roi_crop_node)
    builder.add_node("component_classifier", component_classifier_node)
    builder.add_node("necking_wire", necking_wire_node)
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
    
    # 3. Crop -> Classify
    builder.add_edge("roi_crop", "component_classifier")
    
    # 4. Classify -> Specialist (Necking은 Wire 분석 단일 경로)
    builder.add_edge("component_classifier", "necking_wire")
    
    # 5. Specialist -> Aggregator
    builder.add_edge("necking_wire", "result_aggregator")
    
    # 6. Aggregator -> Manager (Loop Back)
    builder.add_edge("result_aggregator", "hotspot_manager")
    
    # 7. Verdict -> End
    builder.add_edge("verdict", END)
    
    return builder.compile()

def _cleanup_temp_files(temp_image_path: Optional[str], final_state: Optional[Dict[str, Any]]):
    # 원본 임시 파일 삭제
    if temp_image_path and os.path.exists(temp_image_path):
        try:
            os.remove(temp_image_path)
        except Exception:
            pass
            
    # Loop 과정에서 생성된 ROI 파일들 정리 (Best Effort)
    if final_state:
        roi_path = final_state.get("roi_image_path")
        if roi_path and os.path.exists(roi_path) and roi_path != temp_image_path:
             try:
                os.remove(roi_path)
             except Exception:
                pass


def necking_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    import traceback
    temp_image_path = None
    final_state = None
    try:
        
        image_data = extract_image_from_payload(state.get("payload", []))
        if image_data is None:
            return {
                "errors": ["Necking 전문가: 이미지를 추출할 수 없습니다."],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        
        temp_image_path = save_bytes_to_temp_file(image_data)
        
        initial_state: NeckingExpertState = {
            "messages": [],
            "image_path": temp_image_path,
            "hotspots": [],
            "hotspot_queue": None, # Manager가 초기화함
            "analysis_results": [],
            
            # 아래 필드들은 Loop 마다 갱신됨
            "current_hotspot": None,
            "detector_result": None,
            "roi_image_path": None,
            "connection_type": None,
            "specialist_result": None,
            "verdict_report": None,
            "verdict_confidence": None,
            "verdict_result": None
        }
        
        
        graph = build_necking_expert_graph()
        final_state = graph.invoke(initial_state, config={"recursion_limit": 50}) # Loop 고려하여 limit 설정
        
        # 결과 추출
        verdict_report = final_state.get("verdict_report", "")
        verdict_confidence = final_state.get("verdict_confidence", 0)
        verdict_result = final_state.get("verdict_result", {})
        analysis_results = final_state.get("analysis_results", [])
        
        # 증거 수집 (Top 1 기준)
        evidence = []
        if verdict_result:
            visual_desc = verdict_result.get("visual_description", "")
            verdict = verdict_result.get("verdict", "")
            if verdict:
                evidence.append({
                    "evidence": verdict,
                    "details": visual_desc
                })
        
        return {
            "expert_reports": [verdict_report] if verdict_report else ["분석 결과 없음"],
            "expert_analysis_results": {
                "necking": {
                    "multi_hotspot_results": analysis_results,
                    "final_verdict_result": verdict_result
                }
            },
            "expert_confidence_scores": {"necking": verdict_confidence},
            "expert_evidence": {"necking": evidence}
        }
    except Exception as e:
        print(f"\n[ERROR] Necking Expert Wrapper Exception: {str(e)}")
        traceback.print_exc()
        return {
            "errors": [f"Necking 전문가 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }
    finally:
        _cleanup_temp_files(temp_image_path, final_state)
