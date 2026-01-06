"""
Contact 전문가 모듈 (Agent_1 기반)
접촉불량 판별 전문가 - 4단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from src.tools.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 레거시 step1~4 함수 삭제됨 - 새 워크플로우로 대체됨

# 기존 calculate_confidence_score, collect_evidence, generate_report는
# 새 구조에 맞게 수정 예정 (verdict_node에서 사용)

def calculate_confidence_score(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any],
    step4_result: Dict[str, Any]
) -> int:
    """
    신뢰도 점수 계산 (가중치 기반)
    
    Args:
        step1_result: Step 1 분석 결과
        step2_result: Step 2 분석 결과
        step3_result: Step 3 분석 결과
        step4_result: Step 4 분석 결과
        
    Returns:
        신뢰도 점수 (0-100)
    """
    # 각 단계별 점수 추출
    step1_score = step1_result.get("confidence", 0) if not step1_result.get("error") else 0
    step2_score = step2_result.get("confidence", 0) if not step2_result.get("error") else 0
    step3_score = step3_result.get("confidence", 0) if not step3_result.get("error") else 0
    step4_score = step4_result.get("confidence", 0) if not step4_result.get("error") else 0
    
    # 핵심 지표 확인
    is_connection_point = step1_result.get("is_connection_point", False)
    # 하위 호환성: 새로운 필드명과 기존 필드명 모두 확인
    cuprous_oxide_detected = step2_result.get("suspicious_color_pattern_detected", False) or \
                             step2_result.get("cuprous_oxide_detected", False)
    thermal_gradient_detected = step3_result.get("thermal_gradient_detected", False)
    electrical_erosion_detected = step4_result.get("electrical_erosion_detected", False)
    
    # 이미지 품질 평가 (Step 1에서 추출)
    image_quality = step1_result.get("image_quality", "unknown")
    image_quality_penalty = 1.0
    if image_quality == "low":
        image_quality_penalty = 0.7  # 낮은 품질이면 30% 페널티
    elif image_quality == "medium":
        image_quality_penalty = 0.85  # 중간 품질이면 15% 페널티
    
    # 신뢰도 점수 계산 (가중치 적용)
    base_score = 0
    
    # 핵심 지표 가중치
    if is_connection_point:
        base_score += 20
    if cuprous_oxide_detected:
        base_score += 30
    if thermal_gradient_detected:
        base_score += 25
    if electrical_erosion_detected:
        base_score += 15
    
    # 각 단계별 신뢰도 점수의 평균 반영 (10%)
    avg_confidence = (step1_score + step2_score + step3_score + step4_score) / 4
    base_score += avg_confidence * 0.1
    
    # 핵심 3가지가 모두 확인된 경우 (개선된 로직)
    if is_connection_point and cuprous_oxide_detected and thermal_gradient_detected:
        # 무조건 90점이 아니라, 각 단계 신뢰도가 뒷받침될 때만 부스트
        # 핵심 3단계의 평균 신뢰도 계산
        core_avg_confidence = (step1_score + step2_score + step3_score) / 3
        
        # 평균 신뢰도가 높을 때만 가산점 부여
        if core_avg_confidence >= 70:
            # 평균 신뢰도가 70% 이상일 때만 부스트 적용
            boosted_score = base_score * 1.2
            # 최대 98점으로 제한하고, 평균 신뢰도 비율 반영
            base_score = min(98, max(base_score, int(boosted_score * (core_avg_confidence / 100))))
        elif core_avg_confidence >= 50:
            # 평균 신뢰도가 50-70% 사이면 약간의 부스트만 적용
            boosted_score = base_score * 1.1
            base_score = min(85, max(base_score, int(boosted_score * (core_avg_confidence / 100))))
        # 평균 신뢰도가 50% 미만이면 부스트 없음
    
    # 이미지 품질 페널티 적용
    base_score = base_score * image_quality_penalty
    
    return min(100, max(0, int(base_score)))

def collect_evidence(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any],
    step4_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    증거 수집
    
    Args:
        step1_result: Step 1 분석 결과
        step2_result: Step 2 분석 결과
        step3_result: Step 3 분석 결과
        step4_result: Step 4 분석 결과
        
    Returns:
        증거 리스트
    """
    evidence = []
    
    is_connection_point = step1_result.get("is_connection_point", False)
    # 하위 호환성: 새로운 필드명과 기존 필드명 모두 확인
    cuprous_oxide_detected = step2_result.get("suspicious_color_pattern_detected", False) or \
                             step2_result.get("cuprous_oxide_detected", False)
    thermal_gradient_detected = step3_result.get("thermal_gradient_detected", False)
    electrical_erosion_detected = step4_result.get("electrical_erosion_detected", False)
    
    if is_connection_point:
        evidence.append({
            "step": 1,
            "evidence": "접속점 위치 확인",
            "details": step1_result.get("location_description", "")
        })
    if cuprous_oxide_detected:
        suspicion_level = step2_result.get("cuprous_oxide_suspicion_level", "unknown")
        location = step2_result.get("location_of_coloration", "") or \
                   step2_result.get("location_of_oxidation", "")
        evidence.append({
            "step": 2,
            "evidence": f"아산화동 의심 색상 패턴 관찰 (의심도: {suspicion_level})",
            "details": location
        })
    if thermal_gradient_detected:
        evidence.append({
            "step": 3,
            "evidence": "열적 구배 패턴 확인",
            "details": step3_result.get("heat_source_location", "")
        })
    if electrical_erosion_detected:
        evidence.append({
            "step": 4,
            "evidence": "전기적 부식 확인",
            "details": step4_result.get("erosion_pattern", "")
        })
    
    return evidence

def generate_report(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any],
    step4_result: Dict[str, Any],
    confidence_score: int,
    evidence: List[Dict[str, Any]]
) -> str:
    """
    리포트 생성
    
    Args:
        step1_result: Step 1 분석 결과
        step2_result: Step 2 분석 결과
        step3_result: Step 3 분석 결과
        step4_result: Step 4 분석 결과
        confidence_score: 신뢰도 점수
        evidence: 증거 리스트
        
    Returns:
        리포트 텍스트
    """
    is_connection_point = step1_result.get("is_connection_point", False)
    # 하위 호환성: 새로운 필드명과 기존 필드명 모두 확인
    cuprous_oxide_detected = step2_result.get("suspicious_color_pattern_detected", False) or \
                             step2_result.get("cuprous_oxide_detected", False)
    thermal_gradient_detected = step3_result.get("thermal_gradient_detected", False)
    electrical_erosion_detected = step4_result.get("electrical_erosion_detected", False)
    
    # Step 2 결과에서 의심도와 위치 정보 추출 (하위 호환성 고려)
    suspicion_level = step2_result.get("cuprous_oxide_suspicion_level", "unknown")
    location = step2_result.get("location_of_coloration", "") or \
               step2_result.get("location_of_oxidation", "N/A")
    
    report_lines = [
        "[Contact 전문가 리포트]",
        "## 전기 접촉 불량 또는 이물질 접촉으로 인한 화재 가능성 분석 리포트",
        "",
        "**전문가:** 전기 접촉 전문가",
        "",
        "**분석 결과 요약:**",
        f"접촉불량 판정 신뢰도: {confidence_score}%",
        "",
        "**단계별 분석 결과:**",
        "",
        "**1. 위치적 맥락 확인:**",
        f"- 접속점 위치: {step1_result.get('location_type', 'unknown')}",
        f"- 접속점 확인: {'✓ 확인됨' if is_connection_point else '✗ 미확인'}",
        f"- 설명: {step1_result.get('location_description', 'N/A')}",
        f"- 이미지 품질: {step1_result.get('image_quality', 'unknown')} ({step1_result.get('image_quality_reason', 'N/A')})",
        f"- 신뢰도: {step1_result.get('confidence', 0)}%",
        "",
        "**2. 색채 스펙트럼 분석 (아산화동 의심 색상 패턴 관찰):**",
        f"- 아산화동 의심 색상 패턴: {'✓ 관찰됨' if cuprous_oxide_detected else '✗ 미관찰'}",
        f"- 의심도: {suspicion_level}",
        f"- 색상 위치: {location}",
        f"- 신뢰도: {step2_result.get('confidence', 0)}%",
        "",
        "[주의] 일반 RGB 카메라 이미지로는 화학적 성분을 확정할 수 없습니다. ",
        "위 관찰은 아산화동을 의심할 수 있는 색상 패턴일 뿐이며, 화학 분석 없이는 확정 불가능합니다.",
        "",
        "**3. 열적 구배 분석:**",
        f"- 열적 구배 탐지: {'✓ 탐지됨' if thermal_gradient_detected else '✗ 미탐지'}",
        f"- 구배 패턴: {step3_result.get('gradient_pattern', 'unknown')}",
        f"- 열원 위치: {step3_result.get('heat_source_location', 'N/A')}",
        f"- 신뢰도: {step3_result.get('confidence', 0)}%",
        "",
        "**4. 금속 표면 상태 분석 (전기적 부식):**",
        f"- 전기적 부식 탐지: {'✓ 탐지됨' if electrical_erosion_detected else '✗ 미탐지'}",
        f"- 표면 질감: {step4_result.get('surface_texture', 'unknown')}",
        f"- 침식 패턴: {step4_result.get('erosion_pattern', 'N/A')}",
        f"- 신뢰도: {step4_result.get('confidence', 0)}%",
        "",
        "**증거:**"
    ]
    
    for ev in evidence:
        report_lines.append(f"- Step {ev.get('step')}: {ev.get('evidence')} - {ev.get('details', '')}")
    
    report_lines.extend([
        "",
        "**결론:**",
        f"제공된 데이터를 기반으로 분석한 결과, 전기 접촉 불량 또는 이물질 접촉으로 인한 발열이 화재의 주요 원인일 가능성이 {'매우 높습니다' if confidence_score >= 80 else '높습니다' if confidence_score >= 60 else '있습니다'} (신뢰도: {confidence_score}%)."
    ])
    
    return "\n".join(report_lines)


