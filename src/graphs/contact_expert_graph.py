"""
Contact 전문가 서브그래프 빌더
"""
from typing import Dict, Any, Optional, Literal, List
import os

from langgraph.graph import StateGraph, START, END

from src.state import InvestigationState
from src.nodes.contact_nodes import (
    ContactExpertState,
    hotspot_manager_node,
    roi_crop_node,
    component_classifier_node,
    contact_terminal_node,
    contact_splice_node,
    contact_plug_node,
    result_aggregator_node,
    verdict_node
)
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file

def route_loop_manager(state: ContactExpertState) -> Literal["process", "end"]:
    """
    Hotspot Manager 분기: 처리할 Hotspot이 있으면 process, 없으면 end
    """
    if state.get("current_hotspot"):
        return "process"
    return "end"

def route_component_type(state: ContactExpertState) -> Literal["contact_terminal", "contact_splice", "contact_plug", "none"]:
    """
    Component Classification 분기
    """
    conn_type = state.get("connection_type", "None")
    
    if "Terminal" in conn_type or "단자" in conn_type:
        return "contact_terminal"
    elif "Splice" in conn_type or "전선" in conn_type:
        return "contact_splice"
    elif "Plug" in conn_type or "플러그" in conn_type:
        return "contact_plug"
    
    return "none"

def build_contact_expert_graph():
    """Contact 전문가 서브그래프 빌드 - Multi-Hotspot Loop"""
    builder = StateGraph(ContactExpertState)
    
    # 노드 추가
    builder.add_node("hotspot_manager", hotspot_manager_node)
    builder.add_node("roi_crop", roi_crop_node)
    builder.add_node("component_classifier", component_classifier_node)
    
    builder.add_node("contact_terminal", contact_terminal_node)
    builder.add_node("contact_splice", contact_splice_node)
    builder.add_node("contact_plug", contact_plug_node)
    
    builder.add_node("result_aggregator", result_aggregator_node)
    builder.add_node("verdict", verdict_node)
    
    # 엣지 연결
    # 1. Start -> Manager (hotspots는 메인 그래프에서 전달받음)
    builder.add_edge(START, "hotspot_manager")
    
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
    
    # 4. Classify -> Specialist (Branching)
    builder.add_conditional_edges(
        "component_classifier",
        route_component_type,
        {
            "contact_terminal": "contact_terminal",
            "contact_splice": "contact_splice",
            "contact_plug": "contact_plug",
            "none": "result_aggregator" # None도 결과를 기록해야 함
        }
    )
    
    # 5. Specialist -> Aggregator
    builder.add_edge("contact_terminal", "result_aggregator")
    builder.add_edge("contact_splice", "result_aggregator")
    builder.add_edge("contact_plug", "result_aggregator")
    
    # 6. Aggregator -> Manager (Loop Back)
    builder.add_edge("result_aggregator", "hotspot_manager")
    
    # 7. Verdict -> End
    builder.add_edge("verdict", END)
    
    return builder.compile()

def _cleanup_temp_files(temp_image_path: Optional[str], final_state: Optional[Dict[str, Any]]):
    """임시 파일 정리"""
    try:
        # 1. 원본 임시 파일 삭제
        if temp_image_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)
    except Exception:
        pass

    if not final_state:
        return

    # 2. Loop 과정에서 생성된 모든 ROI 파일 정리
    analysis_results = final_state.get("analysis_results", [])
    for res in analysis_results:
        roi_path = res.get("roi_image_path")
        if roi_path and roi_path != temp_image_path and os.path.exists(roi_path):
            try:
                os.remove(roi_path)
            except Exception:
                pass
    
    # 3. State에 마지막으로 남아있는 ROI 경로 정리 (Fallback)
    last_roi_path = final_state.get("roi_image_path")
    if last_roi_path and last_roi_path != temp_image_path and os.path.exists(last_roi_path):
        try:
            os.remove(last_roi_path)
        except Exception:
            pass


def contact_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    temp_image_path = None
    final_state = None
    try:
        
        # [Memory Optimization] Shared Image Path Check
        shared_image_path = state.get("image_path")
        should_cleanup_input = False
        
        if shared_image_path and os.path.exists(shared_image_path):
            temp_image_path = shared_image_path
        else:
            # Fallback for legacy payload
            image_data = extract_image_from_payload(state.get("payload", []))
            if image_data is None:
                return {
                    "errors": ["Contact 전문가: 이미지를 추출할 수 없습니다."],
                    "expert_reports": [],
                    "expert_analysis_results": {},
                    "expert_confidence_scores": {},
                    "expert_evidence": {}
                }
            temp_image_path = save_bytes_to_temp_file(image_data)
            should_cleanup_input = True
        
        # InvestigationState에서 공통 hotspots 읽기
        hotspots = state.get("hotspots", [])
        
        initial_state: ContactExpertState = {
            "messages": [],
            "image_path": temp_image_path,
            "hotspots": hotspots,  # 메인 그래프에서 생성된 공통 hotspots 사용
            "hotspot_queue": None, # Manager가 초기화함
            "analysis_results": [],
            
            # 아래 필드들은 Loop 마다 갱신됨
            "current_hotspot": None,
            "detector_result": None,
            "roi_image_path": None,
            "connection_type": None,
            "terminal_result": None,
            "splice_result": None,
            "plug_result": None,
            "verdict_report": None,
            "verdict_confidence": None,
            "verdict_result": None
        }
        
        
        graph = build_contact_expert_graph()
        final_state = graph.invoke(initial_state, config={"recursion_limit": 50}) # Loop 고려하여 limit 설정
        
        # 결과 추출
        verdict_report = final_state.get("verdict_report", "")
        verdict_confidence = final_state.get("verdict_confidence", 0)
        verdict_result = final_state.get("verdict_result", {})
        analysis_results = final_state.get("analysis_results", [])
        
        # 증거 수집 (Top 1 기준)
        evidence = []
        if verdict_result:
            feature_name = verdict_result.get("feature_name", "")
            observation = verdict_result.get("observation_summary", "")
            if feature_name:
                evidence.append({
                    "evidence": feature_name,
                    "details": observation
                })
        
        return {
            "expert_reports": [verdict_report] if verdict_report else ["분석 결과 없음"],
            "expert_analysis_results": {
                "contact": {
                    "multi_hotspot_results": analysis_results,
                    "final_verdict_result": verdict_result
                }
            },
            "expert_confidence_scores": {"contact": verdict_confidence},
            "expert_evidence": {"contact": evidence}
        }
    except Exception as e:
        import traceback
        print(f"\n[ERROR] Contact Expert Wrapper Exception: {str(e)}")
        traceback.print_exc()
        return {
            "errors": [f"Contact 전문가 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }
    finally:
        # 입력 파일이 우리가 직접 생성한 경우(Fallback)에만 정리
        if should_cleanup_input:
            _cleanup_temp_files(temp_image_path, final_state)
        # Shared Path인 경우, ROI 파일들만 정리 (입력 파일 제외)
        elif final_state:
             # _cleanup_temp_files 로직을 일부 차용하되 입력 파일 삭제 방지
            analysis_results = final_state.get("analysis_results", [])
            for res in analysis_results:
                roi_path = res.get("roi_image_path")
                if roi_path and roi_path != temp_image_path and os.path.exists(roi_path):
                    try:
                        os.remove(roi_path)
                    except Exception:
                        pass
