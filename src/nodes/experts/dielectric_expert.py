"""
DielectricAge 전문가 모듈 (Agent_2 기반)
절연열화 판별 전문가 - 3단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from vertexai.generative_models import Part
from src.nodes.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 프롬프트 정의
STEP1_PROMPT = """당신은 고분자 재료 및 전기 절연 파괴 분석 전문가입니다. 다음 이미지에서 절연체의 탄화 심도와 방향을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 전선 피복의 단면이나 파손 부위를 자세히 관찰하세요.
- 탄화된 절연체와 도체(구리선)의 관계를 객관적으로 식별하세요.
- 탄화의 깊이와 방향을 시각적으로 측정 가능한 형태로 기록하세요.

2단계: 특징 서술
- 탄화된 절연체가 도체에 융착(Fused)되어 있는지 정확히 서술하세요.
- 탄화의 방향성을 구체적으로 서술하세요:
  * 절연체 내부(도체 접촉면)가 심하게 탄화되고 외부 표면은 상대적으로 덜 탄화됨 → 내부 발열(Internal Heating) 징후
  * 표면이 타고 내부가 멀쩡함 → 외부 화재(External Fire) 징후
- 탄화 깊이(deep, shallow, surface_only)를 정확히 서술하세요.

3단계: 논리적 추론
- 외부 화재로 인한 탄화는 표면에서 내부로 진행되며 비교적 균일합니다.
- 절연열화(특히 과전류나 누설전류에 의한)는 도체와 맞닿은 내부에서부터 시작되어 외부로 진행되는 경향이 있습니다.
- 도체와 절연체의 융착은 내부 발열의 강력한 증거입니다.
- 관찰된 탄화 패턴을 종합하여 내부 발열 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "internal_heating_detected": true/false,
    "carbonization_depth": "deep" | "shallow" | "surface_only" | "unknown",
    "carbonization_direction": "internal_to_external" | "external_to_internal" | "uniform" | "unknown",
    "conductor_fusion": true/false,
    "fusion_description": "도체와 절연체의 융착 상태 설명",
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""

STEP2_PROMPT = """당신은 고분자 재료 및 전기 절연 파괴 분석 전문가입니다. 다음 이미지에서 절연체의 스펀지 현상 및 부풀어 오름을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 절연체의 질감과 표면 형태를 자세히 관찰하세요.
- 부풀어 오름, 다공성 구조, 균열 등의 시각적 특징을 객관적으로 식별하세요.
- 각 특징의 위치와 분포를 기록하세요.

2단계: 특징 서술
- 다음 특징을 정확히 서술하세요:
  * 표면이 부풀어 오르거나(Swelling) 다공성(Porous) 구조를 보이는지
  * 스펀지처럼(Sponge-like) 보이는 질감인지
  * 딱딱하게 굳은 균열(Cracking) 외에 부풀어 오른 형상이 있는지
- 질감의 세부 특성을 구체적으로 서술하세요.

3단계: 논리적 추론
- 스펀지 현상과 부풀어 오름은 서서히 진행된 열화(Overheating)의 증거입니다.
- 절연체가 서서히 가열되면서 내부 가스가 방출되면 기공이 형성되어 스펀지처럼 부풀어 오르는 현상이 발생합니다.
- 급격한 외부 화염에 의한 소실과는 다른 질감을 남깁니다.
- 관찰된 질감 특징을 종합하여 절연열화 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "swelling_detected": true/false,
    "spongy_texture_detected": true/false,
    "porous_structure_detected": true/false,
    "texture_description": "질감에 대한 상세 설명",
    "cracking_pattern": "균열 패턴 설명",
    "confidence": 0-100,
    "reasoning": "판단 근거"
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
다음 JSON 형식으로 응답하세요:
{
    "global_aging_detected": true/false,
    "widespread_cracking": true/false,
    "discoloration_pattern": "전체적인 변색 패턴 설명",
    "hardening_detected": true/false,
    "brittleness_detected": true/false,
    "localized_damage_only": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""


def step1_carbonization_depth(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 탄화의 심도 분석"""
    if verbose:
        print("\n🔍 [Step 1] 탄화의 심도 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP1_PROMPT, image_part, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        internal_heating = result.get("internal_heating_detected", False)
        print(f"✅ [Step 1] 완료: 내부 발열 {'탐지됨' if internal_heating else '미탐지'}")
    
    return result


def step2_swelling_analysis(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 스펀지 현상 및 부풀어 오름 분석"""
    if verbose:
        print("\n🎨 [Step 2] 스펀지 현상 및 부풀어 오름 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP2_PROMPT, image_part, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        swelling = result.get("swelling_detected", False) or result.get("spongy_texture_detected", False)
        print(f"✅ [Step 2] 완료: 스펀지/부풀어 오름 {'탐지됨' if swelling else '미탐지'}")
    
    return result


def step3_global_aging(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 광역적 노후화 징후 분석"""
    if verbose:
        print("\n🔥 [Step 3] 광역적 노후화 징후 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP3_PROMPT, image_part, "Step 3", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        global_aging = result.get("global_aging_detected", False)
        print(f"✅ [Step 3] 완료: 광역적 노후화 {'탐지됨' if global_aging else '미탐지'}")
    
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
    
    if internal_heating_detected and swelling_detected and global_aging_detected:
        base_score = max(base_score, 90)
    
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
    image_part = extract_image_from_payload(payload)
    
    if image_part is None:
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
    
    step1_result = step1_carbonization_depth(image_part, verbose)
    step2_result = step2_swelling_analysis(image_part, verbose)
    step3_result = step3_global_aging(image_part, verbose)
    
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

