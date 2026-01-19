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
    builder.add_node("hotspot_manager", hotspot_manager_node)
    builder.add_node("roi_crop", roi_crop_node)
    builder.add_node("component_classifier", component_classifier_node)
    
    builder.add_node("tracking_terminal", tracking_terminal_node)
    builder.add_node("tracking_plug", tracking_plug_node)
    builder.add_node("tracking_pcb", tracking_pcb_node)
    
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

def tracking_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    """InvestigationState와 전문가 서브그래프를 연결하는 래퍼 노드"""
    temp_image_path = None
    final_state = None
    
    try:
        # [Memory Optimization] Shared Image Path Check
        shared_image_path = state.get("image_path")
        should_cleanup_input = False
        
        if shared_image_path and os.path.exists(shared_image_path):
            temp_image_path = shared_image_path
        else:
            # 1. 이미지 추출 (Fallback)
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
            should_cleanup_input = True
        
        # 3. InvestigationState에서 공통 hotspots 읽기
        hotspots = state.get("hotspots", [])
        
        # 4. 초기 상태 설정
        initial_state: TrackingExpertState = {
            "messages": [],
            "image_path": temp_image_path,
            "hotspots": hotspots,  # 메인 그래프에서 생성된 공통 hotspots 사용
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
                 evidence.append({
                     "evidence": "Tracking Signs",
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
        if should_cleanup_input:
            _cleanup_temp_files(temp_image_path, final_state)
        elif final_state:
            # Shared Path인 경우, ROI 파일들만 정리
            analysis_results = final_state.get("analysis_results", [])
            for res in analysis_results:
                roi_path = res.get("roi_image_path")
                if roi_path and roi_path != temp_image_path and os.path.exists(roi_path):
                    try:
                        os.remove(roi_path)
                    except Exception:
                        pass
