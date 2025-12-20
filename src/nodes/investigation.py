"""
화재조사 멀티 에이전트 노드
구조화된 다단계 분석을 수행하는 전문가 노드들을 구현합니다.
"""
from typing import Dict, Optional
from src.state import InvestigationState
from src.nodes.experts.contact_expert import analyze_connection_failure
from src.nodes.experts.dielectric_expert import analyze_insulation_degradation
from src.nodes.experts.mechanical_expert import analyze_mechanical_damage
from src.nodes.experts.tracking_expert import analyze_tracking
from src.nodes.experts.strand_fracture_expert import analyze_strand_fracture


def node_contact(state: InvestigationState) -> Dict:
    """
    접촉불량 전문가 노드 (Agent_1 기반)
    
    Returns:
        Partial State: 전문가 리포트, 분석 결과, 신뢰도 점수, 증거
    """
    try:
        result = analyze_connection_failure(state["payload"], verbose=False)
        
        if "error" in result:
            return {
                "errors": [f"Contact 전문가 오류: {result['error']}"],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        return {
            "expert_reports": [result["report"]],
            "expert_analysis_results": {"contact": result["step_results"]},
            "expert_confidence_scores": {"contact": result["confidence_score"]},
            "expert_evidence": {"contact": result["evidence"]}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"Contact 전문가 노드 실행 중 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }


def node_dielectric(state: InvestigationState) -> Dict:
    """
    절연열화 전문가 노드 (Agent_2 기반)
    
    Returns:
        Partial State: 전문가 리포트, 분석 결과, 신뢰도 점수, 증거
    """
    try:
        result = analyze_insulation_degradation(state["payload"], verbose=False)
        
        if "error" in result:
            return {
                "errors": [f"Dielectric 전문가 오류: {result['error']}"],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        return {
            "expert_reports": [result["report"]],
            "expert_analysis_results": {"dielectric": result["step_results"]},
            "expert_confidence_scores": {"dielectric": result["confidence_score"]},
            "expert_evidence": {"dielectric": result["evidence"]}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"Dielectric 전문가 노드 실행 중 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }


def node_mechanical(state: InvestigationState) -> Dict:
    """
    압착/기계적 손상 전문가 노드 (Agent_3 기반)
    
    Returns:
        Partial State: 전문가 리포트, 분석 결과, 신뢰도 점수, 증거
    """
    try:
        result = analyze_mechanical_damage(state["payload"], verbose=False)
        
        if "error" in result:
            return {
                "errors": [f"Mechanical 전문가 오류: {result['error']}"],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        return {
            "expert_reports": [result["report"]],
            "expert_analysis_results": {"mechanical": result["step_results"]},
            "expert_confidence_scores": {"mechanical": result["confidence_score"]},
            "expert_evidence": {"mechanical": result["evidence"]}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"Mechanical 전문가 노드 실행 중 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }


def node_tracking(state: InvestigationState) -> Dict:
    """
    트래킹 전문가 노드 (Agent_4 기반)
    
    Returns:
        Partial State: 전문가 리포트, 분석 결과, 신뢰도 점수, 증거
    """
    try:
        result = analyze_tracking(state["payload"], verbose=False)
        
        if "error" in result:
            return {
                "errors": [f"Tracking 전문가 오류: {result['error']}"],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        return {
            "expert_reports": [result["report"]],
            "expert_analysis_results": {"tracking": result["step_results"]},
            "expert_confidence_scores": {"tracking": result["confidence_score"]},
            "expert_evidence": {"tracking": result["evidence"]}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"Tracking 전문가 노드 실행 중 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }


def node_strand_fracture(state: InvestigationState) -> Dict:
    """
    반단선 전문가 노드 (Agent_5 기반)
    
    Returns:
        Partial State: 전문가 리포트, 분석 결과, 신뢰도 점수, 증거
    """
    try:
        result = analyze_strand_fracture(state["payload"], verbose=False)
        
        if "error" in result:
            return {
                "errors": [f"StrandFracture 전문가 오류: {result['error']}"],
                "expert_reports": [],
                "expert_analysis_results": {},
                "expert_confidence_scores": {},
                "expert_evidence": {}
            }
        
        return {
            "expert_reports": [result["report"]],
            "expert_analysis_results": {"strand_fracture": result["step_results"]},
            "expert_confidence_scores": {"strand_fracture": result["confidence_score"]},
            "expert_evidence": {"strand_fracture": result["evidence"]}
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "errors": [f"StrandFracture 전문가 노드 실행 중 오류: {str(e)}"],
            "expert_reports": [],
            "expert_analysis_results": {},
            "expert_confidence_scores": {},
            "expert_evidence": {}
        }


