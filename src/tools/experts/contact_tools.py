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

# 프롬프트 정의
from src.prompts.contact_expert_prompts import (
    get_step1_react_prompt,
    get_step2_react_prompt,
    get_step3_react_prompt,
    get_step4_react_prompt
)




def step1_location_context(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 위치적 맥락 확인"""
    # 진행 상황 확인을 위해 항상 출력
    print(f"\n🔍 [Step 1] 위치적 맥락 확인 시작... (이미지: {len(image_data)} bytes)")
    
    # 동적 프롬프트 생성 (이미지 경로는 함수 내부에서는 사용되지 않지만, 프롬프트 포맷팅을 위해 전달할 수도 있음)
    # 현재 구현상 image_path 정보가 이 함수에 없으므로, 프롬프트에서 {image_path} 부분은 생략하거나 placeholder로 처리해야 함.
    # 하지만 새 프롬프트는 image_path를 인자로 받도록 되어 있음.
    # 여기서는 image_path 정보가 없으므로 "Provided Image" 정도로 채워서 전달하거나, 
    # extract_image_from_payload 호출 시점부터 경로를 관리해야 함.
    # 그러나 현재 구조상 bytes만 넘어오므로, "Current Image"로 대체.
    
    prompt = get_step1_react_prompt("Current Image")
    response_text, thinking_info = call_gemini_vision(prompt, image_data, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    # [중요] ReAct 에이전트 무한 루프 방지용 지시문 추가
    result["_analysis_status"] = "COMPLETED"
    result["_instruction_for_agent"] = "Analysis successfully completed. DO NOT CALL tool again. Use this result to generate the Final Answer immediately."
    
    # 결과 필드 추출 (새로운 JSON 구조 대응)
    # 새로운 프롬프트는 "feature_name", "box_2d", "observation_summary", "confidence" 구조를 사용함.
    # 하위 호환성을 위해 기존 구조도 지원하되, 새로운 구조를 우선적으로 사용.
    
    # 새로운 구조: feature_name, box_2d, observation_summary, confidence
    if "feature_name" in result or "box_2d" in result:
        # feature_name을 location_type으로 매핑 (간단한 추론)
        feature_name = result.get("feature_name", "")
        if "나사" in feature_name or "터미널" in feature_name or "단자" in feature_name:
            result["location_type"] = "circuit_breaker_terminal"
            result["is_connection_point"] = True
        elif "전선" in feature_name and ("접속" in feature_name or "꼬임" in feature_name or "커넥터" in feature_name):
            result["location_type"] = "wire_splice"
            result["is_connection_point"] = True
        elif "플러그" in feature_name or "콘센트" in feature_name or "핀" in feature_name:
            result["location_type"] = "outlet_receptor"
            result["is_connection_point"] = True
        elif "중간" in feature_name or "mid" in feature_name.lower():
            result["location_type"] = "mid_span_wire"
            result["is_connection_point"] = False
        else:
            result["location_type"] = "unknown"
            result["is_connection_point"] = False
        
        # location_description은 feature_name과 observation_summary를 조합
        description_parts = []
        if feature_name:
            description_parts.append(f"특징: {feature_name}")
        if "observation_summary" in result:
            # observation_summary의 첫 문장만 사용 (너무 길 수 있음)
            obs_summary = result["observation_summary"]
            if len(obs_summary) > 100:
                obs_summary = obs_summary[:100] + "..."
            description_parts.append(f"소견: {obs_summary}")
        
        result["location_description"] = " | ".join(description_parts) if description_parts else "정보 없음"
        
        # box_2d를 bboxes로 매핑 (하위 호환성)
        if "box_2d" in result:
            result["bboxes"] = [result["box_2d"]]
            result["suspected_origin_box_2d"] = result["box_2d"]
        
        # confidence는 그대로 사용
        if "confidence" not in result:
            result["confidence"] = 50
        
        # reasoning은 observation_summary 사용
        if "observation_summary" in result:
            result["reasoning"] = result["observation_summary"]
    
    # 하위 호환성: 기존 fact_check 구조
    elif "fact_check" in result:
        fact_check = result["fact_check"]
        location_category = fact_check.get("location_category", "unknown")
        physical_contact = fact_check.get("physical_contact", "")
        fusion_detected = fact_check.get("fusion_mark_detected", False)
        
        # location_category를 location_type으로 매핑
        location_type_map = {
            "terminal_end": "circuit_breaker_terminal",
            "mid_span": "mid_span_wire",
            "unknown": "unknown"
        }
        result["location_type"] = location_type_map.get(location_category, "unknown")
        
        # is_connection_point 판단
        is_connection = (
            location_category == "terminal_end" and 
            physical_contact == "touching_metal_connector"
        )
        result["is_connection_point"] = is_connection
        
        # location_description 생성
        description_parts = []
        if fusion_detected:
            description_parts.append("용융흔 감지됨")
        if location_category:
            location_desc_map = {
                "terminal_end": "전선 끝단",
                "mid_span": "전선 중간",
                "unknown": "위치 불명"
            }
            description_parts.append(f"위치: {location_desc_map.get(location_category, location_category)}")
        if physical_contact:
            contact_desc_map = {
                "touching_metal_connector": "금속 체결부 접촉",
                "isolated_in_air": "허공/격리",
                "touching_other_wire": "다른 전선 접촉"
            }
            description_parts.append(f"접촉: {contact_desc_map.get(physical_contact, physical_contact)}")
        
        result["location_description"] = " | ".join(description_parts) if description_parts else "정보 없음"
        result["confidence"] = 75 if fusion_detected else 50
        if "observation_summary" in result:
            result["reasoning"] = result["observation_summary"]
    
    # 하위 호환성: 기존 location_judgment 구조
    elif "location_judgment" in result:
        location_judgment = result["location_judgment"]
        result["is_connection_point"] = location_judgment.get("is_connection_related_position", False)
        result["confidence"] = location_judgment.get("confidence_score", 0)
        result["reasoning"] = location_judgment.get("reasoning_summary", "")
    
    # 하위 호환성: 기존 final_judgment 구조
    elif "final_judgment" in result:
        final_judgment = result["final_judgment"]
        result["is_connection_point"] = final_judgment.get("is_connection_point", False)
        result["confidence"] = final_judgment.get("confidence_score", 0)
        result["reasoning"] = final_judgment.get("reasoning_summary", "")
    
    # 하위 호환성: 기존 spatial_analysis 구조
    if "spatial_analysis" in result and "location_type" not in result:
        spatial_analysis = result["spatial_analysis"]
        result["location_type"] = spatial_analysis.get("component_type", "unknown")
        
        damage_epicenter = spatial_analysis.get("damage_epicenter", "")
        proximity = spatial_analysis.get("proximity_to_interface", "")
        
        description_parts = []
        if damage_epicenter:
            description_parts.append(f"손상 중심: {damage_epicenter}")
        if proximity:
            description_parts.append(f"접속부 근접도: {proximity}")
        
        if "location_description" not in result:
            result["location_description"] = " | ".join(description_parts) if description_parts else "정보 없음"
    
    # 하위 호환성: 기존 visual_evidence 구조
    elif "visual_evidence" in result and "location_type" not in result:
        visual_evidence = result["visual_evidence"]
        result["location_type"] = visual_evidence.get("hotspot_location", "unknown")
        if "location_description" not in result:
            result["location_description"] = f"물리적 결함: {visual_evidence.get('physical_defect', '없음')}"
        
    loc_type = result.get('location_type', 'unknown')
    print(f"✅ [Step 1] 완료: {loc_type}")
    
    return result

def step2_spectral_analysis(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 색채 스펙트럼 분석 (아산화동 의심 색상 패턴 관찰)"""
    # 진행 상황 확인을 위해 항상 출력
    print(f"\n🎨 [Step 2] 색채 스펙트럼 분석 시작... (이미지: {len(image_data)} bytes)")
    
    prompt = get_step2_react_prompt("Current Image")
    response_text, thinking_info = call_gemini_vision(prompt, image_data, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info

    # [중요] ReAct 에이전트 무한 루프 방지용 지시문 추가
    result["_analysis_status"] = "COMPLETED"
    result["_instruction_for_agent"] = "Analysis successfully completed. DO NOT CALL tool again. Use this result to generate the Final Answer immediately."
    
    # 결과 필드 매핑 (새로운 JSON 구조 -> 기존 로직 호환)
    detected = False
    suspicion_level = "none"
    
    if "final_judgment" in result:
        final_judgment = result["final_judgment"]
        detected = final_judgment.get("suspicious_cuprous_oxide", False)
        result["suspicious_color_pattern_detected"] = detected
        suspicion_level = final_judgment.get("probability_level", "none")
        result["cuprous_oxide_suspicion_level"] = suspicion_level
        result["confidence"] = 0 # confidence score가 프롬프트에 명시되지 않았을 수 있음, 기본값
        
        # 새 프롬프트에는 confidence_score가 명시적으로 없음, probability_level로 대체하거나
        # reasoning에서 추출해야 함. 여기선 probability_level 기반 매핑
        if suspicion_level == "high": result["confidence"] = 90
        elif suspicion_level == "medium": result["confidence"] = 70
        elif suspicion_level == "low": result["confidence"] = 40
        else: result["confidence"] = 10

    if "color_analysis" in result:
        color_analysis = result["color_analysis"]
        result["location_of_coloration"] = f"Distribution: {color_analysis.get('distribution', 'unknown')}, Luster: {color_analysis.get('surface_luster', 'unknown')}"
    
    # 결과 요약 항상 출력
    print(f"✅ [Step 2] 완료: 아산화동 의심 색상 패턴 {'관찰됨' if detected else '미관찰'} (의심도: {suspicion_level})")
    
    return result

def step3_thermal_gradient(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 열적 구배 분석"""
    # 진행 상황 확인을 위해 항상 출력 (Hang 여부 확인용)
    print(f"\n🔥 [Step 3] 열적 구배 분석 시작... (이미지: {len(image_data)} bytes)")
    
    prompt = get_step3_react_prompt("Current Image")
    response_text, thinking_info = call_gemini_vision(prompt, image_data, "Step 3", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    # [중요] ReAct 에이전트 무한 루프 방지용 지시문 추가
    result["_analysis_status"] = "COMPLETED"
    result["_instruction_for_agent"] = "Analysis successfully completed. DO NOT CALL tool again. Use this result to generate the Final Answer immediately."
    
    # 결과 필드 매핑
    gradient_detected = False
    
    if "final_judgment" in result:
        final_judgment = result["final_judgment"]
        gradient_detected = final_judgment.get("thermal_gradient_exists", False)
        result["thermal_gradient_detected"] = gradient_detected
        result["confidence"] = final_judgment.get("confidence_score", 0)
        
    if "gradient_analysis" in result:
        gradient_analysis = result["gradient_analysis"]
        result["gradient_pattern"] = gradient_analysis.get("pattern_type", "unknown")
        result["heat_source_location"] = f"Direction: {gradient_analysis.get('direction_of_heat', 'unknown')}"

    # 결과 요약은 항상 출력
    print(f"✅ [Step 3] 완료: 열적 구배 {'탐지됨' if gradient_detected else '미탐지'}")
    
    return result

def step4_surface_analysis(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 4: 금속 표면 상태 분석"""
    # 진행 상황 확인을 위해 항상 출력
    print(f"\n🔬 [Step 4] 금속 표면 상태 분석 시작... (이미지: {len(image_data)} bytes)")
    
    prompt = get_step4_react_prompt("Current Image")
    response_text, thinking_info = call_gemini_vision(prompt, image_data, "Step 4", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    # ReAct 에이전트 루프 방지 (Step 4도 안전장치 추가)
    result["_analysis_status"] = "COMPLETED"
    result["_instruction_for_agent"] = "Analysis successfully completed. DO NOT CALL tool again. Generate Final Answer."
    
    # 결과 필드 매핑
    erosion_detected = False
    
    if "final_judgment" in result:
        final_judgment = result["final_judgment"]
        erosion_detected = final_judgment.get("electrical_erosion_detected", False)
        result["electrical_erosion_detected"] = erosion_detected
        result["confidence"] = final_judgment.get("confidence_score", 0)

    if "surface_features" in result:
        surface_features = result["surface_features"]
        result["surface_texture"] = surface_features.get("texture", "unknown")
        result["erosion_pattern"] = f"Formation: {surface_features.get('formation_type', 'none')}"
    
    # 결과 요약 항상 출력
    print(f"✅ [Step 4] 완료: 전기적 부식 {'탐지됨' if erosion_detected else '미탐지'}")
    
    return result

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

def analyze_connection_failure(payload: List[Any], verbose: bool = False) -> Dict[str, Any]:
    """
    전체 접촉불량 분석 실행 함수
    
    Args:
        payload: LLM 입력 데이터 (이미지 + 텍스트)
        verbose: 상세 로그 출력 여부
        
    Returns:
        분석 결과 딕셔너리
    """
    # payload에서 이미지 추출
    image_data = extract_image_from_payload(payload)
    
    if image_data is None:
        return {
            "error": "이미지를 추출할 수 없습니다.",
            "confidence_score": 0,
            "analysis_summary": "",
            "step_results": {},
            "evidence": [],
            "report": ""
        }
    
    if verbose:
        print(f"\n{'='*60}\n🔍 접촉불량 분석 시작\n{'='*60}")
    
    # 4단계 순차 분석 실행
    step1_result = step1_location_context(image_data, verbose)
    step2_result = step2_spectral_analysis(image_data, verbose)
    step3_result = step3_thermal_gradient(image_data, verbose)
    step4_result = step4_surface_analysis(image_data, verbose)
    
    # 신뢰도 점수 계산
    confidence_score = calculate_confidence_score(
        step1_result, step2_result, step3_result, step4_result
    )
    
    # 증거 수집
    evidence = collect_evidence(step1_result, step2_result, step3_result, step4_result)
    
    # 분석 요약 생성
    is_connection_point = step1_result.get("is_connection_point", False)
    # 하위 호환성: 새로운 필드명과 기존 필드명 모두 확인
    cuprous_oxide_detected = step2_result.get("suspicious_color_pattern_detected", False) or \
                             step2_result.get("cuprous_oxide_detected", False)
    thermal_gradient_detected = step3_result.get("thermal_gradient_detected", False)
    electrical_erosion_detected = step4_result.get("electrical_erosion_detected", False)
    
    suspicion_level = step2_result.get("cuprous_oxide_suspicion_level", "none")
    
    summary_parts = [f"접촉불량 판정 신뢰도: {confidence_score}%"]
    summary_parts.append(
        f"✓ 접속점 위치 확인: {step1_result.get('location_type', 'unknown')}"
        if is_connection_point else "✗ 접속점 위치 미확인"
    )
    summary_parts.append(
        f"✓ 아산화동 의심 색상 패턴 관찰됨 (의심도: {suspicion_level})" if cuprous_oxide_detected else "✗ 아산화동 의심 색상 패턴 미관찰"
    )
    summary_parts.append(
        f"✓ 열적 구배 패턴 확인: {step3_result.get('gradient_pattern', 'unknown')}"
        if thermal_gradient_detected else "✗ 열적 구배 패턴 미확인"
    )
    summary_parts.append(
        f"✓ 전기적 부식 확인: {step4_result.get('surface_texture', 'unknown')}"
        if electrical_erosion_detected else "✗ 전기적 부식 미확인"
    )
    
    analysis_summary = "\n".join(summary_parts)
    
    # 리포트 생성
    report = generate_report(
        step1_result, step2_result, step3_result, step4_result,
        confidence_score, evidence
    )
    
    if verbose:
        print(f"✅ 접촉불량 분석 완료: 신뢰도 {confidence_score}%")
    
    return {
        "confidence_score": confidence_score,
        "analysis_summary": analysis_summary,
        "step_results": {
            "step1": step1_result,
            "step2": step2_result,
            "step3": step3_result,
            "step4": step4_result
        },
        "evidence": evidence,
        "report": report
    }

