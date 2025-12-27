"""
Strand Fracture 전문가 서브그래프 빌더
"""
from typing import Dict, Any, Optional
import os

from langgraph.graph import StateGraph, START

from src.state import InvestigationState
from src.nodes.strand_fracture_nodes import (
    StrandFractureExpertState,
    step1_node,
    step2_node,
    step3_node
)
from src.tools.experts.strand_fracture_tools import (
    calculate_confidence_score,
    collect_evidence,
    generate_report
)
from src.tools.experts.expert_utils import extract_image_from_payload, save_bytes_to_temp_file

def build_strand_fracture_expert_graph():
    """Strand Fracture 전문가 서브그래프 빌드"""
    builder = StateGraph(StrandFractureExpertState)
    
    builder.add_node("step1", step1_node)
    builder.add_node("step2", step2_node)
    builder.add_node("step3", step3_node)
    
    builder.add_edge(START, "step1")
    builder.add_edge("step1", "step2")
    builder.add_edge("step2", "step3")
    
    return builder.compile()

def _cleanup_temp_files(temp_image_path: Optional[str], final_state: Optional[Dict[str, Any]]):
    if temp_image_path and os.path.exists(temp_image_path):
        try:
            os.remove(temp_image_path)
        except Exception:
            pass
    if final_state:
        final_image_path = final_state.get("image_path")
        if final_image_path and final_image_path != temp_image_path and os.path.exists(final_image_path):
            try:
                os.remove(final_image_path)
            except Exception:
                pass

def strand_fracture_expert_wrapper_node(state: InvestigationState) -> Dict[str, Any]:
    import json
    import time
    temp_image_path = None
    final_state = None
    try:
        
        image_data = extract_image_from_payload(state.get("payload", []))
        if image_data is None:
            return {
                "errors": ["Strand Fracture 전문가: 이미지를 추출할 수 없습니다."],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        
        temp_image_path = save_bytes_to_temp_file(image_data)
        
        initial_state: StrandFractureExpertState = {
            "messages": [],
            "image_path": temp_image_path,
            "strand_fracture_step1_result": None,
            "strand_fracture_step2_result": None,
            "strand_fracture_step3_result": None
        }
        
        graph = build_strand_fracture_expert_graph()
        final_state = graph.invoke(initial_state, config={"recursion_limit": 100})
        
        
        step1_result = final_state.get("strand_fracture_step1_result") or {}
        step2_result = final_state.get("strand_fracture_step2_result") or {}
        step3_result = final_state.get("strand_fracture_step3_result") or {}
        
        confidence_score = calculate_confidence_score(step1_result, step2_result, step3_result)
        evidence = collect_evidence(step1_result, step2_result, step3_result)
        report = generate_report(step1_result, step2_result, step3_result, confidence_score, evidence)
        
        return {
            "expert_reports": [report],
            "expert_analysis_results": {
                "strand_fracture": {
                    "step1": step1_result,
                    "step2": step2_result,
                    "step3": step3_result
                }
            },
            "expert_confidence_scores": {"strand_fracture": confidence_score},
            "expert_evidence": {"strand_fracture": evidence}
        }
    except Exception as e:
        return {
            "errors": [f"Strand Fracture 전문가 ReAct 에이전트 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }
    finally:
        _cleanup_temp_files(temp_image_path, final_state)
