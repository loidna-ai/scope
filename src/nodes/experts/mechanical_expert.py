"""
Mechanical 전문가 모듈 (Agent_3 기반)
압착/기계적 손상 판별 전문가 - 3단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from vertexai.generative_models import Part
from src.nodes.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 프롬프트 정의
STEP1_PROMPT = """당신은 기계적 파손 및 재료 역학 분석 전문가입니다. 다음 이미지에서 기계적 변형 흔적을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 전선의 형태와 구조를 자세히 관찰하세요.
- 눌림, 찌그러짐, 압착 흔적 등의 시각적 특징을 객관적으로 식별하세요.
- 도구 흔적(Tool marks), 압착 자국 등의 세부 특징을 기록하세요.

2단계: 특징 서술
- 발견된 기계적 변형을 정확히 서술하세요:
  * 눌린 자국(Compression mark): 압력에 의한 평평한 자국
  * 찌그러짐(Deformation): 전선의 원형 단면이 변형됨
  * 압착 흔적(Crimping mark): 압착 도구에 의한 자국
  * 도구 흔적: 절단, 압착, 또는 기타 기계적 조작의 흔적
- 변형의 위치와 정도를 구체적으로 서술하세요.

3단계: 논리적 추론
- 기계적 변형이 단락흔(Arc bead)과 같은 위치에 있다면, 압착에 의한 단락 가능성이 높습니다.
- 변형 부위와 단락흔의 인과관계를 논리적으로 설명하세요.
- 도구 흔적이 있다면 압착 작업의 직접적 증거가 됩니다.
- 관찰된 변형 패턴을 종합하여 기계적 손상 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "mechanical_deformation_detected": true/false,
    "deformation_type": "compression" | "crimping" | "crushing" | "bending" | "unknown",
    "deformation_location": "변형이 발생한 위치 설명",
    "tool_marks_detected": true/false,
    "tool_mark_description": "도구 흔적에 대한 설명",
    "arc_bead_proximity": "단락흔과 변형 부위의 근접성 설명",
    "causal_relationship": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""

STEP2_PROMPT = """당신은 기계적 파손 및 재료 역학 분석 전문가입니다. 다음 이미지에서 연선의 소선 배열 흐트러짐을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 연선(Stranded Wire)의 소선 배열 상태를 자세히 관찰하세요.
- 소선들이 가지런한지, 퍼져 있는지, 끊어진 상태인지 객관적으로 식별하세요.
- 용융망울 속에 끊어진 소선의 파단면이 포함되어 있는지 확인하세요.

2단계: 특징 서술
- 다음 특징을 정확히 서술하세요:
  * 소선들이 옆으로 퍼지거나(Splay) 부채꼴로 벌어진 상태
  * 끊어진 소선의 파단면이 용융망울 속에 포함되어 있는지
  * 망울이 눌린 전선 모양을 따라 길게 형성되었는지
  * 소선들이 압력에 의해 짓이겨진 상태에서 용융되었는지
- 소선 배열의 정렬 상태를 구체적으로 서술하세요.

3단계: 논리적 추론
- 연선의 경우, 압착이 발생하면 소선들이 물리적 힘에 의해 벌어진 상태에서 용융됩니다.
- 정상적인 단락과 달리 소선들이 자연스럽게 배열되지 않고 강제로 변형된 상태입니다.
- 물리적 힘의 증거가 용융 상태와 일치한다면, 압착에 의한 단락 가능성이 높습니다.
- 관찰된 소선 배열 패턴을 종합하여 기계적 손상 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "strand_splaying_detected": true/false,
    "splay_pattern": "fan_shaped" | "irregular" | "crushed" | "none" | "unknown",
    "broken_strands_in_bead": true/false,
    "bead_shape": "elongated" | "spherical" | "irregular" | "unknown",
    "strand_arrangement": "orderly" | "disordered" | "forced_spread" | "unknown",
    "mechanical_force_evidence": "물리적 힘의 증거 설명",
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""

STEP3_PROMPT = """당신은 기계적 파손 및 재료 역학 분석 전문가입니다. 다음 이미지에서 단락흔(용융망울)의 위치와 구속 상태를 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 용융망울의 위치와 분포를 전체적으로 관찰하세요.
- 망울이 특정 부위에 국한되어 있는지, 확산되어 있는지 객관적으로 식별하세요.
- 가능하다면 전원 측과 부하 측을 구별하여 망울의 위치를 기록하세요.

2단계: 특징 서술
- 용융망울이 특정 기계적 손상 부위에 국한(Confined)되어 있는지 정확히 서술하세요.
- 망울의 분포 패턴(집중, 확산, 산재)을 구체적으로 서술하세요.
- 전원 측과 부하 측 중 어느 쪽에 더 많이 부착되어 있는지 서술하세요.

3단계: 논리적 추론
- 일반적인 단락흔은 전자기력에 의해 튀어나가거나 확산되지만, 압착 단락흔은 눌린 부위에 갇혀 있는 형태를 띨 수 있습니다.
- 단락망울이 전원 측보다는 부하 측(Load Side)에 상대적으로 많이 부착되는 경향이 있습니다.
- 망울이 특정 위치에 고정되어 있고 확산되지 않은 경우, 물리적 구속이 있었을 가능성이 높습니다.
- 관찰된 망울 위치와 분포를 종합하여 기계적 구속 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "bead_confinement_detected": true/false,
    "confinement_location": "망울이 구속된 위치 설명",
    "bead_distribution": "load_side" | "source_side" | "both" | "unknown",
    "bead_spread": "confined" | "spread" | "scattered" | "unknown",
    "mechanical_constraint_evidence": "물리적 구속의 증거 설명",
    "load_side_concentration": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""


def step1_mechanical_deformation(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 기계적 변형 흔적 분석"""
    if verbose:
        print("\n🔍 [Step 1] 기계적 변형 흔적 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP1_PROMPT, image_part, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        deformation_detected = result.get("mechanical_deformation_detected", False)
        print(f"✅ [Step 1] 완료: 기계적 변형 {'탐지됨' if deformation_detected else '미탐지'}")
    
    return result


def step2_strand_splaying(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 소선 배열의 흐트러짐 분석"""
    if verbose:
        print("\n🎨 [Step 2] 소선 배열의 흐트러짐 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP2_PROMPT, image_part, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        splaying_detected = result.get("strand_splaying_detected", False)
        print(f"✅ [Step 2] 완료: 소선 흐트러짐 {'탐지됨' if splaying_detected else '미탐지'}")
    
    return result


def step3_bead_confinement(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 단락흔의 위치와 구속 분석"""
    if verbose:
        print("\n🔥 [Step 3] 단락흔의 위치와 구속 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP3_PROMPT, image_part, "Step 3", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        confinement_detected = result.get("bead_confinement_detected", False)
        print(f"✅ [Step 3] 완료: 망울 구속 {'탐지됨' if confinement_detected else '미탐지'}")
    
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
    
    mechanical_deformation_detected = step1_result.get("mechanical_deformation_detected", False)
    causal_relationship = step1_result.get("causal_relationship", False)
    tool_marks_detected = step1_result.get("tool_marks_detected", False)
    strand_splaying_detected = step2_result.get("strand_splaying_detected", False)
    bead_confinement_detected = step3_result.get("bead_confinement_detected", False)
    
    base_score = 0
    
    if mechanical_deformation_detected:
        base_score += 30
    if causal_relationship:
        base_score += 25
    if tool_marks_detected:
        base_score += 15
    if strand_splaying_detected:
        base_score += 20
    if bead_confinement_detected:
        base_score += 10
    
    avg_confidence = (step1_score + step2_score + step3_score) / 3
    base_score += avg_confidence * 0.1
    
    if mechanical_deformation_detected and causal_relationship and (strand_splaying_detected or bead_confinement_detected):
        base_score = max(base_score, 90)
    
    return min(100, max(0, int(base_score)))


def collect_evidence(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """증거 수집"""
    evidence = []
    
    mechanical_deformation_detected = step1_result.get("mechanical_deformation_detected", False)
    causal_relationship = step1_result.get("causal_relationship", False)
    tool_marks_detected = step1_result.get("tool_marks_detected", False)
    strand_splaying_detected = step2_result.get("strand_splaying_detected", False)
    bead_confinement_detected = step3_result.get("bead_confinement_detected", False)
    
    if mechanical_deformation_detected:
        evidence.append({
            "step": 1,
            "evidence": "기계적 변형 확인",
            "details": step1_result.get("deformation_location", "")
        })
    if causal_relationship:
        evidence.append({
            "step": 1,
            "evidence": "인과 관계 확인",
            "details": step1_result.get("arc_bead_proximity", "")
        })
    if tool_marks_detected:
        evidence.append({
            "step": 1,
            "evidence": "도구 흔적 확인",
            "details": step1_result.get("tool_mark_description", "")
        })
    if strand_splaying_detected:
        evidence.append({
            "step": 2,
            "evidence": "소선 흐트러짐 확인",
            "details": step2_result.get("mechanical_force_evidence", "")
        })
    if bead_confinement_detected:
        evidence.append({
            "step": 3,
            "evidence": "망울 구속 확인",
            "details": step3_result.get("mechanical_constraint_evidence", "")
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
    mechanical_deformation_detected = step1_result.get("mechanical_deformation_detected", False)
    causal_relationship = step1_result.get("causal_relationship", False)
    tool_marks_detected = step1_result.get("tool_marks_detected", False)
    strand_splaying_detected = step2_result.get("strand_splaying_detected", False)
    bead_confinement_detected = step3_result.get("bead_confinement_detected", False)
    
    report_lines = [
        "[Mechanical 전문가 리포트]",
        "## 압착/기계적 손상 판별 전문가 리포트",
        "",
        "**전문가:** 기계적 손상 분석 전문가",
        "",
        "**분석 결과 요약:**",
        f"압착/기계적 손상 판정 신뢰도: {confidence_score}%",
        "",
        "**단계별 분석 결과:**",
        "",
        "**1. 기계적 변형 흔적 분석:**",
        f"- 기계적 변형 탐지: {'✓ 탐지됨' if mechanical_deformation_detected else '✗ 미탐지'}",
        f"- 변형 유형: {step1_result.get('deformation_type', 'unknown')}",
        f"- 변형 위치: {step1_result.get('deformation_location', 'N/A')}",
        f"- 인과 관계: {'✓ 확인됨' if causal_relationship else '✗ 미확인'}",
        f"- 도구 흔적: {'✓ 확인됨' if tool_marks_detected else '✗ 미확인'}",
        f"- 신뢰도: {step1_result.get('confidence', 0)}%",
        "",
        "**2. 소선 배열의 흐트러짐 분석:**",
        f"- 소선 흐트러짐 탐지: {'✓ 탐지됨' if strand_splaying_detected else '✗ 미탐지'}",
        f"- 흐트러짐 패턴: {step2_result.get('splay_pattern', 'unknown')}",
        f"- 소선 배열: {step2_result.get('strand_arrangement', 'unknown')}",
        f"- 신뢰도: {step2_result.get('confidence', 0)}%",
        "",
        "**3. 단락흔의 위치와 구속 분석:**",
        f"- 망울 구속 탐지: {'✓ 탐지됨' if bead_confinement_detected else '✗ 미탐지'}",
        f"- 망울 분포: {step3_result.get('bead_distribution', 'unknown')}",
        f"- 망울 확산: {step3_result.get('bead_spread', 'unknown')}",
        f"- 신뢰도: {step3_result.get('confidence', 0)}%",
        "",
        "**증거:**"
    ]
    
    for ev in evidence:
        report_lines.append(f"- Step {ev.get('step')}: {ev.get('evidence')} - {ev.get('details', '')}")
    
    report_lines.extend([
        "",
        "**결론:**",
        f"제공된 데이터를 기반으로 분석한 결과, 압착 또는 기계적 손상에 의한 단락 가능성이 {'매우 높습니다' if confidence_score >= 80 else '높습니다' if confidence_score >= 60 else '있습니다'} (신뢰도: {confidence_score}%)."
    ])
    
    return "\n".join(report_lines)


def analyze_mechanical_damage(payload: List[Any], verbose: bool = False) -> Dict[str, Any]:
    """
    전체 압착/기계적 손상 분석 실행 함수
    
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
        print(f"\n{'='*60}\n🔍 압착/기계적 손상 분석 시작\n{'='*60}")
    
    step1_result = step1_mechanical_deformation(image_part, verbose)
    step2_result = step2_strand_splaying(image_part, verbose)
    step3_result = step3_bead_confinement(image_part, verbose)
    
    confidence_score = calculate_confidence_score(step1_result, step2_result, step3_result)
    evidence = collect_evidence(step1_result, step2_result, step3_result)
    
    mechanical_deformation_detected = step1_result.get("mechanical_deformation_detected", False)
    causal_relationship = step1_result.get("causal_relationship", False)
    tool_marks_detected = step1_result.get("tool_marks_detected", False)
    strand_splaying_detected = step2_result.get("strand_splaying_detected", False)
    bead_confinement_detected = step3_result.get("bead_confinement_detected", False)
    
    summary_parts = [f"압착/기계적 손상 판정 신뢰도: {confidence_score}%"]
    summary_parts.append(
        f"✓ 기계적 변형 확인: {step1_result.get('deformation_type', 'unknown')}"
        if mechanical_deformation_detected else "✗ 기계적 변형 미확인"
    )
    summary_parts.append(
        "✓ 인과 관계 확인 (변형 부위와 단락흔 일치)"
        if causal_relationship else "✗ 인과 관계 미확인"
    )
    summary_parts.append(
        "✓ 도구 흔적 확인" if tool_marks_detected else "✗ 도구 흔적 미확인"
    )
    summary_parts.append(
        f"✓ 소선 흐트러짐 확인: {step2_result.get('splay_pattern', 'unknown')}"
        if strand_splaying_detected else "✗ 소선 흐트러짐 미확인"
    )
    summary_parts.append(
        f"✓ 망울 구속 확인: {step3_result.get('bead_distribution', 'unknown')}"
        if bead_confinement_detected else "✗ 망울 구속 미확인"
    )
    
    analysis_summary = "\n".join(summary_parts)
    report = generate_report(step1_result, step2_result, step3_result, confidence_score, evidence)
    
    if verbose:
        print(f"✅ 압착/기계적 손상 분석 완료: 신뢰도 {confidence_score}%")
    
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

