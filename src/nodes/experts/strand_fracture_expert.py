"""
StrandFracture 전문가 모듈 (Agent_5 기반)
반단선 판별 전문가 - 3단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from vertexai.generative_models import Part
from src.nodes.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 프롬프트 정의
STEP1_PROMPT = """당신은 금속 재료 공학 및 화재 감식 전문가입니다. 제공된 현미경 이미지를 분석하여 전선 용융흔(망울)의 형태학적 특징을 파악하는 것이 목표입니다.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[분석 목표]
이미지에서 개별 소선(Strand)의 끝단(Tip) 형태를 정밀하게 분석하여 반단선(Semi-disconnection) 여부를 판단할 수 있는 근거를 마련하십시오.

[단계별 분석 프로세스 (Chain of Thought)]
1단계: 시각적 요소 추출
- 연선(Stranded Wire)의 각 소선 끝단을 개별적으로 관찰하세요.
- 끝단의 형태(뾰족함, 둥글림, 융합 등)를 객관적으로 식별하세요.
- 네킹(Necking) 현상이 있는지 확인하세요.

2단계: 특징 서술
- 다음 특징을 정확히 서술하세요:
  * 개별 소선이 명확히 구별되는지(Individual strands detected)
  * 끝단이 뾰족한지(Tapered tips) 둥근지(Blunt)
  * 끝단에 미세 용융망울(Micro-bead)이 있는지
  * 네킹 현상(끝단이 좁아지는 현상)이 있는지
- 끝단의 형태학적 특징을 구체적으로 서술하세요.

3단계: 논리적 추론
- 반단선은 소선이 부분적으로 끊어지면서 끝단이 뾰족하게 형성되는 경향이 있습니다.
- 네킹 현상은 소선이 끊어지기 전에 좁아지는 현상으로, 반단선의 특징입니다.
- 끝단에 미세 망울이 있다면 부분적 용융이 발생했음을 의미합니다.
- 관찰된 끝단 형태를 종합하여 반단선 여부를 논리적으로 판단하세요.

[출력 형식]
반드시 아래의 JSON 스키마를 준수하여 응답하십시오. Markdown 코드 블록(```json)을 포함하지 말고 순수 JSON 텍스트만 출력하는 것을 권장합니다.
{
    "individual_strands_detected": true/false,
    "tapered_tips_detected": true/false,
    "micro_bead_at_tip": true/false,
    "thermal_discoloration": true/false,
    "necking_phenomenon": true/false,
    "tip_morphology": "tapered" | "blunt" | "fused" | "mixed" | "unknown",
    "strand_separation": true/false,
    "necking_description": "네킹, 미세 용융, 열변색에 대한 상세 관찰 내용",
    "confidence": 0-100,
    "reasoning": "판단 근거 요약"
}"""

STEP2_PROMPT = """당신은 금속 재료 공학 및 화재 감식 전문가입니다. 제공된 현미경 이미지를 분석하여 전선 용융흔(망울)의 형태학적 특징을 파악하는 것이 목표입니다.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[분석 목표]
이미지에서 '용융망울(Beads)'의 **크기**와 **분포**를 정밀하게 분석하여 반단선(Semi-disconnection) 여부를 판단할 수 있는 근거를 마련하십시오.

[단계별 분석 프로세스 (Chain of Thought)]
1단계: 시각적 요소 추출
2단계: 특징 서술
- 개별 소선(Strand) 끝마다 좁쌀 형태의 미세 망울(Micro-beads)이 있는지 확인하십시오.
- 망울들이 서로 뭉쳐있는지(Clustered) 개별적으로 산재해 있는지(Individual/Scattered) 확인하십시오.

3단계: 논리적 추론
- 반단선 아크는 에너지가 국부적이고 상대적으로 작아, 전선 전체를 녹이는 거대 망울보다는 소선 끝에 맺힌 미세 망울을 형성하는 경향이 있습니다.
- 관찰된 크기와 분포가 이 특징과 일치하는지 평가하십시오.

[출력 형식]
반드시 아래의 JSON 스키마를 준수하여 응답하십시오. Markdown 코드 블록(```json)을 포함하지 말고 순수 JSON 텍스트만 출력하는 것을 권장합니다.
{
    "micro_beads_detected": true,
    "bead_size": "micro",
    "bead_distribution": "individual_strands",
    "bead_count": "many",
    "bead_description": "상세 관찰 내용...",
    "large_bead_present": false,
    "confidence": 95,
    "reasoning": "소선 끝마다 좁쌀 형태의 작은 망울들이 다수 관찰되며 거대 망울이 부재하므로..."
}"""

STEP3_PROMPT = """당신은 금속 파단면 분석 및 전기 배선 손상 전문가입니다. 제공된 현미경 이미지를 분석하여 전선의 '기계적 피로(Mechanical Fatigue)' 흔적을 식별하는 것이 목표입니다.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[분석 목표]
이미지에서 전선 피복의 손상 상태와 굽힘/비틀림 흔적을 정밀하게 분석하여, 반단선(Semi-disconnection) 발생 가능성을 기계적 관점에서 판단하십시오.

[단계별 분석 프로세스 (Chain of Thought)]
1단계: 시각적 요소 추출
- 전선 피복(Insulation)에 균열(Cracking), 마모(Wear), 또는 소성 변형(Deformation)이 있는지 객관적으로 관찰하십시오.
2단계: 특징 서술
- 손상 부위가 스트레인 릴리프(Strain relief, 플러그 목 부분)나 자주 꺾이는 굴곡점(Bend point)인지 확인하십시오.
- 해당 위치에서 소선들이 끊어졌는지 확인하여 기계적 스트레스와의 연관성을 파악하십시오.
3단계: 논리적 추론
- 반단선은 주로 코드가 자주 꺾이거나 비틀리는 부분에서 기계적 피로 누적으로 인해 발생합니다.
- 피로 흔적의 위치(피복 손상 부위)와 소선 파단 위치가 일치한다면 반단선 가능성이 매우 높습니다.

[출력 형식]
반드시 아래의 JSON 스키마를 준수하여 응답하십시오. Markdown 코드 블록(```json)을 포함하지 말고 순수 JSON 텍스트만 출력하는 것을 권장합니다.
{
    "mechanical_fatigue_detected": true,
    "fatigue_location": "strain_relief",
    "insulation_damage": true,
    "insulation_damage_type": "cracking",
    "bending_evidence": true,
    "location_match": true,
    "fatigue_description": "플러그 목 부분의 피복에 깊은 균열이 관찰되며...",
    "confidence": 92,
    "reasoning": "스트레인 릴리프 부위의 피복 균열과 소선 파단 위치가 일치하여 반복적 굽힘에 의한 피로 파괴로 판단됨."
}"""


def step1_tip_morphology(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 소선 끝단의 형상 분석"""
    if verbose:
        print("\n🔍 [Step 1] 소선 끝단의 형상 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP1_PROMPT, image_part, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        tapered_tips = result.get("tapered_tips_detected", False)
        print(f"✅ [Step 1] 완료: 뾰족한 끝단 {'탐지됨' if tapered_tips else '미탐지'}")
    
    return result


def step2_bead_distribution(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 용융망울의 크기와 분포 분석"""
    if verbose:
        print("\n🔍 [Step 2] 용융망울의 크기와 분포 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP2_PROMPT, image_part, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        micro_beads = result.get("micro_beads_detected", False)
        print(f"✅ [Step 2] 완료: 미세 망울 {'탐지됨' if micro_beads else '미탐지'}")
    
    return result


def step3_mechanical_fatigue(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 기계적 피로 흔적 분석"""
    if verbose:
        print("\n🔍 [Step 3] 기계적 피로 흔적 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP3_PROMPT, image_part, "Step 3", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        fatigue = result.get("mechanical_fatigue_detected", False)
        print(f"✅ [Step 3] 완료: 기계적 피로 {'탐지됨' if fatigue else '미탐지'}")
    
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
    
    individual_strands = step1_result.get("individual_strands_detected", False)
    tapered_tips = step1_result.get("tapered_tips_detected", False)
    necking_phenomenon = step1_result.get("necking_phenomenon", False)
    micro_beads = step2_result.get("micro_beads_detected", False)
    no_large_bead = not step2_result.get("large_bead_present", True)
    mechanical_fatigue = step3_result.get("mechanical_fatigue_detected", False)
    location_match = step3_result.get("location_match", False)
    
    base_score = 0
    
    # 핵심 지표 가중치
    if individual_strands:
        base_score += 20
    if tapered_tips:
        base_score += 30  # 뾰족한 끝단이 가장 중요한 증거
    if necking_phenomenon:
        base_score += 25
    if micro_beads:
        base_score += 20
    if no_large_bead:
        base_score += 10
    if mechanical_fatigue:
        base_score += 15
    if location_match:
        base_score += 10
    
    # 각 단계별 신뢰도 점수의 평균 반영 (10%)
    avg_confidence = (step1_score + step2_score + step3_score) / 3
    base_score += avg_confidence * 0.1
    
    # 핵심 조합에 따른 보정
    if tapered_tips and micro_beads and mechanical_fatigue:
        base_score = max(base_score, 90)
    
    if necking_phenomenon and micro_beads:
        base_score = max(base_score, 85)
    
    return min(100, max(0, int(base_score)))


def collect_evidence(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """증거 수집"""
    evidence = []
    
    individual_strands = step1_result.get("individual_strands_detected", False)
    tapered_tips = step1_result.get("tapered_tips_detected", False)
    necking_phenomenon = step1_result.get("necking_phenomenon", False)
    micro_beads = step2_result.get("micro_beads_detected", False)
    mechanical_fatigue = step3_result.get("mechanical_fatigue_detected", False)
    
    if individual_strands:
        evidence.append({
            "step": 1,
            "evidence": "개별 소선 확인",
            "details": step1_result.get("necking_description", "")
        })
    if tapered_tips:
        evidence.append({
            "step": 1,
            "evidence": "뾰족한 끝단 확인",
            "details": step1_result.get("necking_description", "")
        })
    if necking_phenomenon:
        evidence.append({
            "step": 1,
            "evidence": "네킹 현상 확인",
            "details": step1_result.get("necking_description", "")
        })
    if micro_beads:
        evidence.append({
            "step": 2,
            "evidence": "미세 망울 확인",
            "details": step2_result.get("bead_description", "")
        })
    if mechanical_fatigue:
        evidence.append({
            "step": 3,
            "evidence": "기계적 피로 확인",
            "details": step3_result.get("fatigue_description", "")
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
    individual_strands = step1_result.get("individual_strands_detected", False)
    tapered_tips = step1_result.get("tapered_tips_detected", False)
    necking_phenomenon = step1_result.get("necking_phenomenon", False)
    micro_beads = step2_result.get("micro_beads_detected", False)
    mechanical_fatigue = step3_result.get("mechanical_fatigue_detected", False)
    
    report_lines = [
        "[StrandFracture 전문가 리포트]",
        "## 반단선 (Semi-disconnection) 판별 전문가 리포트",
        "",
        "**전문가:** 반단선 분석 전문가",
        "",
        "**분석 결과 요약:**",
        f"반단선 판정 신뢰도: {confidence_score}%",
        "",
        "**단계별 분석 결과:**",
        "",
        "**1. 소선 끝단의 형상 분석:**",
        f"- 개별 소선 확인: {'✓ 확인됨' if individual_strands else '✗ 미확인'}",
        f"- 뾰족한 끝단: {'✓ 탐지됨' if tapered_tips else '✗ 미탐지'}",
        f"- 네킹 현상: {'✓ 확인됨' if necking_phenomenon else '✗ 미확인'}",
        f"- 끝단 형태: {step1_result.get('tip_morphology', 'unknown')}",
        f"- 신뢰도: {step1_result.get('confidence', 0)}%",
        "",
        "**2. 용융망울의 크기와 분포 분석:**",
        f"- 미세 망울 탐지: {'✓ 탐지됨' if micro_beads else '✗ 미탐지'}",
        f"- 망울 크기: {step2_result.get('bead_size', 'unknown')}",
        f"- 망울 분포: {step2_result.get('bead_distribution', 'unknown')}",
        f"- 거대 망울 존재: {'✗ 없음' if not step2_result.get('large_bead_present', True) else '✓ 있음'}",
        f"- 신뢰도: {step2_result.get('confidence', 0)}%",
        "",
        "**3. 기계적 피로 흔적 분석:**",
        f"- 기계적 피로 탐지: {'✓ 탐지됨' if mechanical_fatigue else '✗ 미탐지'}",
        f"- 피로 위치: {step3_result.get('fatigue_location', 'unknown')}",
        f"- 피복 손상: {'✓ 확인됨' if step3_result.get('insulation_damage', False) else '✗ 미확인'}",
        f"- 위치 일치: {'✓ 일치' if step3_result.get('location_match', False) else '✗ 불일치'}",
        f"- 신뢰도: {step3_result.get('confidence', 0)}%",
        "",
        "**증거:**"
    ]
    
    for ev in evidence:
        report_lines.append(f"- Step {ev.get('step')}: {ev.get('evidence')} - {ev.get('details', '')}")
    
    report_lines.extend([
        "",
        "**결론:**",
        f"제공된 데이터를 기반으로 분석한 결과, 반단선에 의한 단락 가능성이 {'매우 높습니다' if confidence_score >= 80 else '높습니다' if confidence_score >= 60 else '있습니다'} (신뢰도: {confidence_score}%)."
    ])
    
    return "\n".join(report_lines)


def analyze_strand_fracture(payload: List[Any], verbose: bool = False) -> Dict[str, Any]:
    """
    전체 반단선 분석 실행 함수
    
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
        print(f"\n{'='*60}\n🔍 반단선 분석 시작\n{'='*60}")
    
    step1_result = step1_tip_morphology(image_part, verbose)
    step2_result = step2_bead_distribution(image_part, verbose)
    step3_result = step3_mechanical_fatigue(image_part, verbose)
    
    confidence_score = calculate_confidence_score(step1_result, step2_result, step3_result)
    evidence = collect_evidence(step1_result, step2_result, step3_result)
    
    individual_strands = step1_result.get("individual_strands_detected", False)
    tapered_tips = step1_result.get("tapered_tips_detected", False)
    necking_phenomenon = step1_result.get("necking_phenomenon", False)
    micro_beads = step2_result.get("micro_beads_detected", False)
    mechanical_fatigue = step3_result.get("mechanical_fatigue_detected", False)
    
    summary_parts = [f"반단선 판정 신뢰도: {confidence_score}%"]
    summary_parts.append(
        "✓ 개별 소선 확인" if individual_strands else "✗ 개별 소선 미확인"
    )
    summary_parts.append(
        "✓ 뾰족한 끝단 확인" if tapered_tips else "✗ 뾰족한 끝단 미확인"
    )
    summary_parts.append(
        "✓ 네킹 현상 확인" if necking_phenomenon else "✗ 네킹 현상 미확인"
    )
    summary_parts.append(
        "✓ 미세 망울 확인" if micro_beads else "✗ 미세 망울 미확인"
    )
    summary_parts.append(
        "✓ 기계적 피로 확인" if mechanical_fatigue else "✗ 기계적 피로 미확인"
    )
    
    analysis_summary = "\n".join(summary_parts)
    report = generate_report(step1_result, step2_result, step3_result, confidence_score, evidence)
    
    if verbose:
        print(f"✅ 반단선 분석 완료: 신뢰도 {confidence_score}%")
    
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

