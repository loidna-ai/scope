"""
전문가 노드 공통 리포트 유틸리티
보고서 포맷팅 및 Hotspot 추출 함수를 제공합니다.
"""
import re
from typing import List, Dict, Any, Callable, Optional
from src.utils.logging_config import setup_logger

logger = setup_logger(__name__)


def format_report_summary(
    assessments: List[Dict[str, Any]],
    expert_type: str = "necking",
    component_filter_func: Optional[Callable[[str], bool]] = None
) -> str:
    """
    구조화된 요약 보고서 생성 (Map-Reduce용)
    Workers의 preliminary_assessments를 바탕으로 Debate용 요약 생성
    
    Args:
        assessments: Worker 리포트 리스트
        expert_type: 전문가 타입 ("necking", "deform", "contact")
        component_filter_func: 컴포넌트 타입 필터 함수 (None이면 기본 필터 사용)
    
    Returns:
        포맷팅된 보고서 텍스트
    """
    if not assessments:
        return "분석된 증거 없음"
    
    # 전문가 타입별 기본 필터 함수
    if component_filter_func is None:
        if expert_type == "contact":
            component_filter_func = lambda ct: (
                "Terminal" in ct or "Splice" in ct or "Plug" in ct or ct == "Unknown"
            )
        else:  # necking, deform
            component_filter_func = lambda ct: "Wire" in ct or ct == "Unknown"
    
    summary = "=== Worker Reports Summary ===\n"
    for assessment in assessments:
        hotspot_id = assessment.get('id', 'unknown')
        
        # New WorkerReport Structure Handling
        if "facts" in assessment and "opinion" in assessment:
            facts = assessment['facts']
            opinion = assessment['opinion']
            
            # Extract basic info safely
            verdict = opinion.get('verdict', 'N/A')
            confidence = opinion.get('confidence', 0)
            conn_type = assessment.get('_connection_type', 'Unknown')
            
            summary += f"\n[Worker Report #{hotspot_id}] (Type: {conn_type})\n"
            
            # [Logic] 전문가 타입별 필터링
            if not component_filter_func(conn_type):
                skip_message = (
                    "Analysis Skipped (Target is not a Contact Component)" 
                    if expert_type == "contact" 
                    else "Analysis Skipped (Target is not a Wire)"
                )
                summary += f"⚠️ NOTE: {skip_message}\n"
                summary += "-"*40 + "\n"
                continue
            
            # [Added] 에러 상태인 경우 요약에 표시
            if "error" in facts:
                summary += f"⚠️ NOTE: Analysis Failed (Error: {facts['error']})\n"
                summary += "-"*40 + "\n"
                continue

            summary += f"1. FACTS (Evidence):\n"
            
            # 전문가 타입별 Facts 필드 출력
            if expert_type in ["necking", "deform"]:
                # Wire 관련 필드들
                summary += f"  - Global Arrangement: {facts.get('global_arrangement', 'N/A')}\n"
                summary += f"  - Fire Pattern: {facts.get('fire_pattern', 'N/A')}\n"
                summary += f"  - Location: {facts.get('identified_location', 'N/A')}\n"
                summary += f"  - Crop: {facts.get('crop_description', 'N/A')}\n"
                summary += f"  - Reference Shaft Shape: {facts.get('reference_shaft_shape_observation', 'N/A')}\n"
                summary += f"  - Surface: {facts.get('surface_visual_check', 'N/A')}\n"
                summary += f"  - Width Change: {facts.get('width_change_observation', 'N/A')}\n"
                summary += f"  - Boundary: {facts.get('boundary_visual_check', 'N/A')}\n"
                summary += f"  - Terminal Shape: {facts.get('terminal_shape_observation', 'N/A')}\n"
                summary += f"  - Terminal Width: {facts.get('terminal_width_comparison', 'N/A')}\n"
                summary += f"  - Strand State: {facts.get('strand_state_observation', 'N/A')}\n"
                summary += f"  - Bead Scan (Zone4): {facts.get('bead_scan', 'N/A')}\n"
            elif expert_type == "contact":
                # Contact 관련 필드들
                summary += f"  - Visual Description: {facts.get('visual_description', 'N/A')}\n"

            summary += f"2. OPINION (Verdict):\n"
            summary += f"  - Verdict: {verdict}\n"
            summary += f"  - Confidence: {confidence}\n"
            summary += f"  - Reasoning: {opinion.get('reasoning', 'N/A')}\n"
            
            # necking, deform의 경우 추가 필드
            if expert_type in ["necking", "deform"]:
                summary += f"  - Supporting Logic: {opinion.get('supporting_logic', 'N/A')}\n"
                summary += f"  - Refuting Logic: {opinion.get('refuting_logic', 'N/A')}\n"
            
            summary += "-"*40 + "\n"
            
        else:
            # Fallback for old structure or error
            observations = assessment.get('observations', 'N/A')
            severity_score = assessment.get('severity_score', 0)
            evidence_quality = assessment.get('evidence_quality', 'unknown')
            is_critical = assessment.get('is_critical', False)
            connection_type = assessment.get('_connection_type', 'Unknown')
            
            risk_level = "🔴 HIGH" if is_critical else ("🟡 MEDIUM" if evidence_quality == "medium" else "🟢 LOW")
            
            summary += f"- [{hotspot_id}] Type: {connection_type} | Risk: {risk_level} | Score: {severity_score}\n"
            summary += f"  Obs: {observations}\n"
    
    return summary


def extract_critiqued_hotspots(critique: str, all_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Critic의 지적에서 언급된 특정 Hotspot ID 추출
    
    Args:
        critique: Critic의 비평 텍스트
        all_results: 전체 분석 결과 리스트
    
    Returns:
        Critic이 언급한 Hotspot들의 분석 결과 리스트
    """
    if not critique or not all_results:
        return []
    
    # "Spot #3", "Hotspot #7", "#2" 등 패턴 추출
    mentioned_ids = set()
    patterns = [
        r'[Ss]pot\s*#?(\d+)',
        r'[Hh]otspot\s*#?(\d+)',
        r'#(\d+)',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, critique)
        mentioned_ids.update(int(m) for m in matches)
    
    if not mentioned_ids:
        # Critic이 특정 Hotspot을 언급하지 않으면 전체 반환
        return all_results
    
    # 언급된 ID만 필터링
    filtered = [
        res for res in all_results 
        if res.get('hotspot_info', {}).get('id') in mentioned_ids or res.get('id') in mentioned_ids
    ]
    
    logger.info(f"Focus: Critic highlighted hotspots: {sorted(mentioned_ids)}")
    
    return filtered if filtered else all_results
