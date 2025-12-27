"""
DielectricAge 전문가 모듈 (Agent_2 기반)
절연열화 판별 전문가 - 3단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from src.tools.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 프롬프트 정의
STEP1_PROMPT = """당신은 고분자 재료 및 전기 절연 파괴 분석 전문가입니다. 다음 이미지에서 절연체의 탄화 심도와 방향을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[주의 사항]
- **시각적 한계 인식**: 2D 이미지, 특히 겉모습만 찍힌 사진에서 '내부에서 외부로의 탄화(Internal to External)'를 판독하는 것은 매우 어렵습니다.
- **단면(Cross-section) 확인 필요**: 전선의 절단면이 명확히 보이지 않아 내부와 외부를 비교할 수 없다면, '판단 불가' 또는 'unknown'으로 처리하고 신뢰도를 낮추세요.
- **추측 금지**: 겉만 보고 내부 발열을 추측하지 마세요. 단면이 보이지 않으면 신뢰도를 낮게 설정하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출 및 이미지 품질 평가
- 먼저 이미지에서 전선의 단면(Cross-section)이나 파손 부위가 명확히 보이는지 평가하세요.
- 단면이 보이지 않거나 내부와 외부를 구분할 수 없다면, 이를 명시하고 신뢰도를 낮추세요.
- 전선 피복의 단면이나 파손 부위를 자세히 관찰하세요.
- 탄화된 절연체와 도체(구리선)의 관계를 객관적으로 식별하세요.
- 탄화의 깊이와 방향을 시각적으로 측정 가능한 형태로 기록하세요.

2단계: 특징 서술
- 탄화된 절연체가 도체에 융착(Fused)되어 있는지 정확히 서술하세요.
- 탄화의 방향성을 구체적으로 서술하세요:
  * 절연체 내부(도체 접촉면)가 심하게 탄화되고 외부 표면은 상대적으로 덜 탄화됨 → 내부 발열(Internal Heating) 징후
  * 표면이 타고 내부가 멀쩡함 → 외부 화재(External Fire) 징후
- 탄화 깊이(deep, shallow, surface_only)를 정확히 서술하세요.
- **단면이 보이지 않는 경우**: 내부와 외부를 구분할 수 없으므로 방향성을 'unknown'으로 설정하고 신뢰도를 낮추세요.

3단계: 논리적 추론
- 외부 화재로 인한 탄화는 표면에서 내부로 진행되며 비교적 균일합니다.
- 절연열화(특히 과전류나 누설전류에 의한)는 도체와 맞닿은 내부에서부터 시작되어 외부로 진행되는 경향이 있습니다.
- 도체와 절연체의 융착은 내부 발열의 강력한 증거입니다.
- **단면이 보이지 않는 경우**: 내부 발열 판단이 불가능하므로 신뢰도를 낮게 설정하세요.
- 관찰된 탄화 패턴을 종합하여 내부 발열 여부를 논리적으로 판단하세요.

[출력 형식]
식별된 특징의 위치를 나타내는 Bounding Box 좌표(0~1000 정규화 좌표, [ymin, xmin, ymax, xmax])를 포함하여 다음 JSON 형식으로 응답하세요:
{
    "internal_heating_detected": true/false,
    "carbonization_depth": "deep" | "shallow" | "surface_only" | "unknown",
    "carbonization_direction": "internal_to_external" | "external_to_internal" | "uniform" | "unknown",
    "conductor_fusion": true/false,
    "fusion_description": "도체와 절연체의 융착 상태 설명",
    "cross_section_visible": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거 (단면이 보이지 않는 경우 이를 명시)",
    "bboxes": [[ymin, xmin, ymax, xmax]]
}"""

STEP2_PROMPT = """당신은 고분자 재료 및 전기 절연 파괴 분석 전문가입니다. 다음 이미지에서 절연체의 표면 질감을 분석하여 스펀지 현상, 흑연화, 단순 용융을 구분하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[주의 사항]
- **질감 구분의 중요성**: 단순히 거친 표면을 스펀지 현상으로 단정하지 마세요. 구멍(Pore)의 깊이감이 확인되어야 합니다.
- **오탐지 방지**: 탄화된 수지는 원래 거칠기 때문에, 거친 표면만으로는 스펀지 현상이라고 판단할 수 없습니다.
- **비교 분석**: 질감이 다공성(스펀지)인지, 광택이 나는 흑연화인지, 단순히 녹아내린 것인지 명확히 구분하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 절연체의 질감과 표면 형태를 자세히 관찰하세요.
- 표면의 광택도, 질감, 구조 등을 객관적으로 식별하세요.
- 각 특징의 위치와 분포를 기록하세요.

2단계: 특징 서술 (비교/대조 분석)
- 절연체 표면의 질감을 다음 기준에 따라 냉정하게 분류하세요:
  
  **A. 스펀지형(Spongy) - 절연열화 징후:**
  - 내부 가스 방출로 인해 부풀어 오르고 구멍이 숭숭 뚫린 무광택 상태
  - 다공성(Porous) 구조가 명확히 보임
  - 구멍의 깊이감이 시각적으로 확인 가능
  
  **B. 흑연화(Graphitized) - 트래킹 징후:**
  - 표면이 매끄럽고 금속처럼 반짝이는 광택 상태
  - 검은색이지만 광택이 나는 특성
  - 스펀지형과는 정반대의 질감
  
  **C. 단순 용융(Melted):**
  - 열에 의해 흘러내려 굳은 매끄러운 상태
  - 광택이 있지만 흑연화와는 다른 특성
  - 부풀어 오르지 않고 평평한 표면
  
  **D. 단순 거칠기(Rough):**
  - 탄화로 인한 자연스러운 거칠기
  - 구멍이 없고 단순히 표면이 거친 상태
  - 스펀지 현상이 아님
  
- [중요] 단순히 거친 표면을 스펀지 현상으로 단정하지 마세요. 구멍의 깊이감과 다공성 구조가 명확히 확인되어야 합니다.
- 질감의 세부 특성을 구체적으로 서술하세요.

3단계: 논리적 추론
- 스펀지 현상과 부풀어 오름은 서서히 진행된 열화(Overheating)의 증거입니다.
- 절연체가 서서히 가열되면서 내부 가스가 방출되면 기공이 형성되어 스펀지처럼 부풀어 오르는 현상이 발생합니다.
- 흑연화는 트래킹(전기적 트래킹)의 징후이며, 스펀지 현상과는 다른 메커니즘입니다.
- 단순 용융은 급격한 과열에 의한 것이며, 스펀지 현상과는 구별됩니다.
- 관찰된 질감 특징을 종합하여 절연열화 여부를 논리적으로 판단하세요.

[출력 형식]
식별된 특징의 위치를 나타내는 Bounding Box 좌표(0~1000 정규화 좌표, [ymin, xmin, ymax, xmax])를 포함하여 다음 JSON 형식으로 응답하세요:
{
    "swelling_detected": true/false,
    "spongy_texture_detected": true/false,
    "porous_structure_detected": true/false,
    "graphitization_detected": true/false,
    "melted_texture_detected": true/false,
    "texture_type": "spongy" | "graphitized" | "melted" | "rough" | "unknown",
    "texture_description": "질감에 대한 상세 설명 (스펀지형 vs 흑연화 vs 용융 구분 포함)",
    "cracking_pattern": "균열 패턴 설명",
    "confidence": 0-100,
    "reasoning": "판단 근거 (질감 구분 근거 포함)",
    "bboxes": [[ymin, xmin, ymax, xmax]]
}"""

STEP3_PROMPT = """당신은 고분자 재료 및 전기 절연 파괴 분석 전문가입니다. 다음 이미지에서 광역적 노후화 징후를 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 단락흔 주변뿐만 아니라 이미지 내 전선 전체를 관찰하세요.
- 균열, 변색, 경화 등의 시각적 특징을 객관적으로 식별하세요.
- 각 특징의 분포 범위를 기록하세요.

2단계: 특징 서술
- 다음 광역적 노후화 징후를 정확히 서술하세요:
  * 전선 전체가 갈라지거나(Cracking) 색상이 바랜(Discolored) 패턴
  * 전선 전체의 경화(Hardening) 현상
  * 취성(Brittleness) - 피복이 유연성을 잃고 뚝뚝 끊어질 듯한 균열이 전반적으로 분포
- 손상이 국소적인지 광역적인지 구체적으로 서술하세요.

3단계: 논리적 추론
- 절연열화는 특정 지점에만 국한되지 않고 배선 전체에 걸쳐 진행되는 경우가 많습니다.
- 전선 전체의 경화/균열과 함께 도체 부근의 집중적인 내부 탄화가 관찰되면 절연열화에 의한 단락으로 판정할 수 있습니다.
- 만약 단락흔 주변만 타고 나머지는 깨끗하다면 절연열화보다는 기계적 손상이나 일시적 요인일 가능성이 높습니다.
- 관찰된 노후화 패턴을 종합하여 광역적 노후화 여부를 논리적으로 판단하세요.

[출력 형식]
식별된 특징의 위치를 나타내는 Bounding Box 좌표(0~1000 정규화 좌표, [ymin, xmin, ymax, xmax])를 포함하여 다음 JSON 형식으로 응답하세요:
{
    "global_aging_detected": true/false,
    "widespread_cracking": true/false,
    "discoloration_pattern": "전체적인 변색 패턴 설명",
    "hardening_detected": true/false,
    "brittleness_detected": true/false,
    "localized_damage_only": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거",
    "bboxes": [[ymin, xmin, ymax, xmax]]
}"""

def step1_carbonization_depth(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 탄화의 심도 분석"""
    if verbose:
        print("\n🔍 [Step 1] 탄화의 심도 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP1_PROMPT, image_data, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        internal_heating = result.get("internal_heating_detected", False)
        print(f"✅ [Step 1] 완료: 내부 발열 {'탐지됨' if internal_heating else '미탐지'}")
    
    # ReAct 에이전트 무한 루프 방지용 강제 종료 신호
    result["_analysis_status"] = "COMPLETED"
    result["_instruction_for_agent"] = "Analysis successfully completed. DO NOT CALL tool again. Use this result to generate the Final Answer immediately."
    
    return result

def step2_swelling_analysis(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 스펀지 현상 및 부풀어 오름 분석"""
    if verbose:
        print("\n🎨 [Step 2] 스펀지 현상 및 부풀어 오름 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP2_PROMPT, image_data, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        swelling = result.get("swelling_detected", False) or result.get("spongy_texture_detected", False)
        print(f"✅ [Step 2] 완료: 스펀지/부풀어 오름 {'탐지됨' if swelling else '미탐지'}")
    
    # ReAct 에이전트 무한 루프 방지용 강제 종료 신호
    result["_analysis_status"] = "COMPLETED"
    result["_instruction_for_agent"] = "Analysis successfully completed. DO NOT CALL tool again. Use this result to generate the Final Answer immediately."
    
    return result

def step3_global_aging(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 광역적 노후화 징후 분석"""
    if verbose:
        print("\n🔥 [Step 3] 광역적 노후화 징후 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP3_PROMPT, image_data, "Step 3", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        global_aging = result.get("global_aging_detected", False)
        print(f"✅ [Step 3] 완료: 광역적 노후화 {'탐지됨' if global_aging else '미탐지'}")
    
    # ReAct 에이전트 무한 루프 방지용 강제 종료 신호
    result["_analysis_status"] = "COMPLETED"
    result["_instruction_for_agent"] = "Analysis successfully completed. DO NOT CALL tool again. Use this result to generate the Final Answer immediately."
    
    return result

def calculate_confidence_score(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any]
) -> int:
    """신뢰도 점수 계산 (가중치 기반)"""
    step1_score = step1_result.get("confidence", 0) if not step1_result.get("error") else 0
    step2_score = step2_result.get("confidence", 0) if not step2_result.get("error") else 0
    step3_score = step3_result.get("confidence", 0) if not step3_result.get("error") else 0
    
    internal_heating_detected = step1_result.get("internal_heating_detected", False)
    conductor_fusion = step1_result.get("conductor_fusion", False)
    swelling_detected = step2_result.get("swelling_detected", False) or step2_result.get("spongy_texture_detected", False)
    global_aging_detected = step3_result.get("global_aging_detected", False)
    
    base_score = 0
    
    if internal_heating_detected:
        base_score += 35
    if conductor_fusion:
        base_score += 20
    if swelling_detected:
        base_score += 25
    if global_aging_detected:
        base_score += 20
    
    avg_confidence = (step1_score + step2_score + step3_score) / 3
    base_score += avg_confidence * 0.1
    
    # 절연열화인데 전선 나머지 부분이 새것처럼 깨끗하다? -> 기계적 손상이나 일시적 과전류일 확률이 높음
    # 광역 노후화가 없으면 절연열화 확신을 20% 차감 (Penalty)
    if not global_aging_detected:
        base_score = int(base_score * 0.8)
    
    # 부스트 로직 완화 (Contact 전문가와 동일한 방식)
    if internal_heating_detected and swelling_detected and global_aging_detected:
        # 핵심 3단계의 평균 신뢰도 계산
        core_avg_confidence = (step1_score + step2_score + step3_score) / 3
        
        # 평균 신뢰도가 높을 때만 가산점 부여
        if core_avg_confidence >= 70:
            boosted_score = base_score * 1.2
            base_score = min(98, max(base_score, int(boosted_score * (core_avg_confidence / 100))))
        elif core_avg_confidence >= 50:
            boosted_score = base_score * 1.1
            base_score = min(85, max(base_score, int(boosted_score * (core_avg_confidence / 100))))
        # 평균 신뢰도가 50% 미만이면 부스트 없음
    
    return min(100, max(0, int(base_score)))

def collect_evidence(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """증거 수집"""
    evidence = []
    
    internal_heating_detected = step1_result.get("internal_heating_detected", False)
    conductor_fusion = step1_result.get("conductor_fusion", False)
    swelling_detected = step2_result.get("swelling_detected", False) or step2_result.get("spongy_texture_detected", False)
    global_aging_detected = step3_result.get("global_aging_detected", False)
    
    if internal_heating_detected:
        evidence.append({
            "step": 1,
            "evidence": "내부 발열 확인",
            "details": step1_result.get("fusion_description", "")
        })
    if conductor_fusion:
        evidence.append({
            "step": 1,
            "evidence": "도체 융착 확인",
            "details": step1_result.get("fusion_description", "")
        })
    if swelling_detected:
        evidence.append({
            "step": 2,
            "evidence": "스펀지/부풀어 오름 현상 확인",
            "details": step2_result.get("texture_description", "")
        })
    if global_aging_detected:
        evidence.append({
            "step": 3,
            "evidence": "광역적 노후화 확인",
            "details": step3_result.get("discoloration_pattern", "")
        })
    
    return evidence

def generate_report(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any],
    confidence_score: int,
    evidence: List[Dict[str, Any]]
) -> str:
    """리포트 생성"""
    internal_heating_detected = step1_result.get("internal_heating_detected", False)
    conductor_fusion = step1_result.get("conductor_fusion", False)
    swelling_detected = step2_result.get("swelling_detected", False) or step2_result.get("spongy_texture_detected", False)
    global_aging_detected = step3_result.get("global_aging_detected", False)
    
    report_lines = [
        "[DielectricAge 전문가 리포트]",
        "## 절연열화 (Insulation Degradation) 판별 전문가 리포트",
        "",
        "**전문가:** 절연열화 분석 전문가",
        "",
        "**분석 결과 요약:**",
        f"절연열화 판정 신뢰도: {confidence_score}%",
        "",
        "**단계별 분석 결과:**",
        "",
        "**1. 탄화의 심도 분석:**",
        f"- 내부 발열 탐지: {'✓ 탐지됨' if internal_heating_detected else '✗ 미탐지'}",
        f"- 탄화 방향: {step1_result.get('carbonization_direction', 'unknown')}",
        f"- 탄화 깊이: {step1_result.get('carbonization_depth', 'unknown')}",
        f"- 도체 융착: {'✓ 확인됨' if conductor_fusion else '✗ 미확인'}",
        f"- 신뢰도: {step1_result.get('confidence', 0)}%",
        "",
        "**2. 스펀지 현상 및 부풀어 오름 분석:**",
        f"- 스펀지/부풀어 오름 탐지: {'✓ 탐지됨' if swelling_detected else '✗ 미탐지'}",
        f"- 질감 유형: {step2_result.get('texture_type', 'unknown')}",
        f"- 흑연화 탐지: {'✓ 탐지됨 (트래킹 징후 가능)' if step2_result.get('graphitization_detected', False) else '✗ 미탐지'}",
        f"- 질감 설명: {step2_result.get('texture_description', 'N/A')}",
        f"- 신뢰도: {step2_result.get('confidence', 0)}%",
        "",
        "**3. 광역적 노후화 징후 분석:**",
        f"- 광역적 노후화 탐지: {'✓ 탐지됨' if global_aging_detected else '✗ 미탐지'}",
        f"- 광역적 균열: {step3_result.get('widespread_cracking', False)}",
        f"- 변색 패턴: {step3_result.get('discoloration_pattern', 'N/A')}",
        f"- 신뢰도: {step3_result.get('confidence', 0)}%",
        "",
        "**증거:**"
    ]
    
    for ev in evidence:
        report_lines.append(f"- Step {ev.get('step')}: {ev.get('evidence')} - {ev.get('details', '')}")
    
    report_lines.extend([
        "",
        "**결론:**",
        f"제공된 데이터를 기반으로 분석한 결과, 절연열화에 의한 단락 가능성이 {'매우 높습니다' if confidence_score >= 80 else '높습니다' if confidence_score >= 60 else '있습니다'} (신뢰도: {confidence_score}%)."
    ])
    
    return "\n".join(report_lines)

def analyze_insulation_degradation(payload: List[Any], verbose: bool = False) -> Dict[str, Any]:
    """
    전체 절연열화 분석 실행 함수
    
    Args:
        payload: LLM 입력 데이터 (이미지 + 텍스트)
        verbose: 상세 로그 출력 여부
        
    Returns:
        분석 결과 딕셔너리
    """
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
        print(f"\n{'='*60}\n🔍 절연열화 분석 시작\n{'='*60}")
    
    step1_result = step1_carbonization_depth(image_data, verbose)
    step2_result = step2_swelling_analysis(image_data, verbose)
    step3_result = step3_global_aging(image_data, verbose)
    
    confidence_score = calculate_confidence_score(step1_result, step2_result, step3_result)
    evidence = collect_evidence(step1_result, step2_result, step3_result)
    
    internal_heating_detected = step1_result.get("internal_heating_detected", False)
    conductor_fusion = step1_result.get("conductor_fusion", False)
    swelling_detected = step2_result.get("swelling_detected", False) or step2_result.get("spongy_texture_detected", False)
    global_aging_detected = step3_result.get("global_aging_detected", False)
    
    summary_parts = [f"절연열화 판정 신뢰도: {confidence_score}%"]
    summary_parts.append(
        f"✓ 내부 발열 확인: {step1_result.get('carbonization_direction', 'unknown')}"
        if internal_heating_detected else "✗ 내부 발열 미확인"
    )
    summary_parts.append(
        "✓ 도체 융착 확인" if conductor_fusion else "✗ 도체 융착 미확인"
    )
    summary_parts.append(
        "✓ 스펀지/부풀어 오름 현상 확인" if swelling_detected else "✗ 스펀지/부풀어 오름 현상 미확인"
    )
    summary_parts.append(
        f"✓ 광역적 노후화 확인: {step3_result.get('widespread_cracking', False)}"
        if global_aging_detected else "✗ 광역적 노후화 미확인"
    )
    
    analysis_summary = "\n".join(summary_parts)
    report = generate_report(step1_result, step2_result, step3_result, confidence_score, evidence)
    
    if verbose:
        print(f"✅ 절연열화 분석 완료: 신뢰도 {confidence_score}%")
    
    return {
        "confidence_score": confidence_score,
        "analysis_summary": analysis_summary,
        "step_results": {
            "step1": step1_result,
            "step2": step2_result,
            "step3": step3_result
        },
        "evidence": evidence,
        "report": report
    }

