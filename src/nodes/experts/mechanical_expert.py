"""
Mechanical 전문가 모듈 (Agent_3 기반)
압착/기계적 손상 판별 전문가 - 3단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from src.nodes.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 프롬프트 정의
STEP1_PROMPT = """당신은 기계적 파손 및 재료 역학 분석 전문가입니다. 다음 이미지에서 기계적 변형 흔적을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[치명적 주의사항]
- **열에 의한 변형과 냉간 변형 구분 필수**: 화재 열에 의해 구리가 녹아서 흘러내리거나(Flow), 굳으면서 수축된 주름(Shrinkage)을 '도구 흔적'이나 '기계적 변형'으로 오인하지 마세요.
- **용융망울 자체의 불규칙한 모양은 기계적 손상 증거가 아님**: 용융망울(Bead) 자체의 찌그러짐, 납작해짐, 불규칙한 형상은 중력이나 표면장력에 의한 열 변형(Thermal Deformation)일 가능성이 높습니다.
- **기계적 변형 판정 기준**: '기계적 변형'으로 판정하려면, **용융되지 않은 피복이나 도체 부분**에 명확한 '찍힘(Indentations)', '절단면(Cut marks)', '압착 자국(Crimping marks)'이 있어야 합니다.
- **냉간 변형(Cold Deformation)만 인정**: 도체가 아직 고체 상태일 때 가해진 물리적 힘에 의한 변형만 기계적 손상으로 인정하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출 및 변형 유형 구분
- 먼저 관찰된 변형이 **열에 의한 변형(Thermal)**인지 **냉간 변형(Cold)**인지 구분하세요.
- 용융되지 않은 피복이나 도체 부분을 중심으로 관찰하세요.
- 다음을 객관적으로 식별하세요:
  * 찍힘(Indentations): 도구나 물체에 눌린 자국
  * 절단면(Cut marks): 날카로운 도구에 의해 잘린 흔적
  * 압착 자국(Crimping marks): 압착 도구에 의한 규칙적인 패턴
  * 도구 흔적(Tool marks): 플라이어, 절단기 등에 의한 흔적
- **용융망울 자체의 불규칙한 형상은 기록하지 마세요** (이는 열 변형입니다).

2단계: 특징 서술
- 발견된 **냉간 변형**을 정확히 서술하세요:
  * 찍힘(Indentations): 압력에 의한 움푹 패인 자국 (용융 전에 형성됨)
  * 절단면(Cut marks): 날카롭게 잘린 흔적
  * 압착 흔적(Crimping marks): 압착 도구에 의한 규칙적인 자국
  * 도구 흔적: 플라이어, 절단기 등에 의한 명확한 패턴
- 변형이 **용융되지 않은 부분**에 있는지 확인하세요.
- 변형의 위치와 정도를 구체적으로 서술하세요.
- **용융망울의 불규칙한 형상은 기계적 변형으로 기록하지 마세요**.

3단계: 논리적 추론
- 기계적 변형이 **용융되지 않은 피복이나 도체 부분**에 있고, 단락흔(Arc bead)과 같은 위치에 있다면, 압착에 의한 단락 가능성이 높습니다.
- 변형 부위와 단락흔의 인과관계를 논리적으로 설명하세요.
- 도구 흔적이 있다면 압착 작업의 직접적 증거가 됩니다.
- **용융망울 자체의 찌그러짐이나 납작해짐은 기계적 손상 증거가 아닙니다**.
- 관찰된 변형 패턴을 종합하여 기계적 손상 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "mechanical_deformation_detected": true/false,
    "deformation_type": "compression" | "crimping" | "crushing" | "cut" | "indentation" | "unknown",
    "deformation_location": "변형이 발생한 위치 설명 (용융되지 않은 부분인지 명시)",
    "deformation_on_non_melted_part": true/false,
    "tool_marks_detected": true/false,
    "tool_mark_description": "도구 흔적에 대한 설명",
    "arc_bead_proximity": "단락흔과 변형 부위의 근접성 설명",
    "causal_relationship": true/false,
    "thermal_deformation_excluded": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거 (열 변형과 냉간 변형 구분 근거 포함)"
}"""

STEP2_PROMPT = """당신은 기계적 파손 및 재료 역학 분석 전문가입니다. 다음 이미지에서 연선의 소선 배열 흐트러짐을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[주의 사항]
- **자연스러운 흐트러짐 vs 강제 변형 구분**: 화재가 진행되면 피복이 타면서 소선은 자연스럽게 풀립니다. 단순히 퍼진 것만으로는 기계적 손상 증거가 되지 않습니다.
- **강제 변형의 증거 필요**: 소선이 **날카롭게 잘려나간(Cut)** 상태에서 융착되었는지, 또는 **강한 힘에 의해 납작하게 눌린(Crushed)** 상태인지 확인해야 합니다.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 연선(Stranded Wire)의 소선 배열 상태를 자세히 관찰하세요.
- 소선들이 가지런한지, 퍼져 있는지, 끊어진 상태인지 객관적으로 식별하세요.
- 용융망울 속에 끊어진 소선의 파단면이 포함되어 있는지 확인하세요.
- 소선이 **날카롭게 잘린(Cut)** 흔적이 있는지 확인하세요.
- 소선이 **납작하게 눌린(Crushed)** 상태인지 확인하세요.

2단계: 특징 서술 (자연스러운 흐트러짐 vs 강제 변형 구분)
- 다음 특징을 정확히 서술하세요:
  * 소선들이 옆으로 퍼지거나(Splay) 부채꼴로 벌어진 상태
  * **소선이 날카롭게 잘려나간(Cut) 흔적이 있는지** (강제 변형의 증거)
  * **소선이 납작하게 눌린(Crushed) 상태인지** (압착의 증거)
  * 끊어진 소선의 파단면이 용융망울 속에 포함되어 있는지
  * 망울이 눌린 전선 모양을 따라 길게 형성되었는지
  * 소선들이 압력에 의해 짓이겨진 상태에서 용융되었는지
- 소선 배열의 정렬 상태를 구체적으로 서술하세요.
- **자연스러운 흐트러짐인지, 강제로 변형된 것인지 구분하세요**.

3단계: 논리적 추론
- 연선의 경우, 압착이 발생하면 소선들이 물리적 힘에 의해 벌어진 상태에서 용융됩니다.
- 정상적인 단락과 달리 소선들이 자연스럽게 배열되지 않고 강제로 변형된 상태입니다.
- **날카롭게 잘린 흔적이나 납작하게 눌린 흔적**이 있다면 강제 변형의 증거입니다.
- 단순히 퍼진 것만으로는 증거가 되지 않습니다. 피복이 타면서 자연스럽게 풀릴 수 있습니다.
- 물리적 힘의 증거가 용융 상태와 일치한다면, 압착에 의한 단락 가능성이 높습니다.
- 관찰된 소선 배열 패턴을 종합하여 기계적 손상 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "strand_splaying_detected": true/false,
    "splay_pattern": "fan_shaped" | "irregular" | "crushed" | "cut" | "natural" | "none" | "unknown",
    "cut_marks_detected": true/false,
    "crushed_state_detected": true/false,
    "broken_strands_in_bead": true/false,
    "bead_shape": "elongated" | "spherical" | "flattened" | "irregular" | "unknown",
    "strand_arrangement": "orderly" | "disordered" | "forced_spread" | "natural_spread" | "unknown",
    "mechanical_force_evidence": "물리적 힘의 증거 설명 (자연스러운 흐트러짐인지 강제 변형인지 구분)",
    "confidence": 0-100,
    "reasoning": "판단 근거 (자연스러운 흐트러짐 vs 강제 변형 구분 근거 포함)"
}"""

STEP3_PROMPT = """당신은 기계적 파손 및 재료 역학 분석 전문가입니다. 다음 이미지에서 단락흔(용융망울)의 위치와 구속 상태를 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[주의 사항]
- **망울 형상의 중요성**: 압착된 좁은 틈에서 아크가 터지면 망울이 밖으로 튀어나가지 못하고 전선 사이에 끼어서 납작해진(Flattened) 형태를 띱니다.
- **구형 vs 납작한 형태 구분**: 일반적인 단락흔은 둥근 구형(Spherical)이지만, 압착 단락흔은 납작해진(Flattened) 형태일 수 있습니다.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 용융망울의 위치와 분포를 전체적으로 관찰하세요.
- 망울이 특정 부위에 국한되어 있는지, 확산되어 있는지 객관적으로 식별하세요.
- **망울의 형상을 구체적으로 관찰하세요**: 둥근 구형(Spherical)인지, 납작해진(Flattened) 형태인지 확인하세요.
- 가능하다면 전원 측과 부하 측을 구별하여 망울의 위치를 기록하세요.

2단계: 특징 서술
- 용융망울이 특정 기계적 손상 부위에 국한(Confined)되어 있는지 정확히 서술하세요.
- **망울의 형상**: 둥근 구형(Spherical)인지, 납작해진(Flattened) 형태인지 구체적으로 서술하세요.
- 망울이 전선 사이에 끼어서 납작해진 형태인지 확인하세요.
- 망울의 분포 패턴(집중, 확산, 산재)을 구체적으로 서술하세요.
- 전원 측과 부하 측 중 어느 쪽에 더 많이 부착되어 있는지 서술하세요.

3단계: 논리적 추론
- 일반적인 단락흔은 전자기력에 의해 튀어나가거나 확산되어 둥근 구형(Spherical)을 띱니다.
- 압착 단락흔은 눌린 부위에 갇혀 있어 납작해진(Flattened) 형태를 띨 수 있습니다.
- **망울이 구형이 아니라 납작해진 형태**라면, 물리적 구속이 있었을 가능성이 높습니다.
- 단락망울이 전원 측보다는 부하 측(Load Side)에 상대적으로 많이 부착되는 경향이 있습니다.
- 망울이 특정 위치에 고정되어 있고 확산되지 않은 경우, 물리적 구속이 있었을 가능성이 높습니다.
- 관찰된 망울 위치와 분포를 종합하여 기계적 구속 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "bead_confinement_detected": true/false,
    "confinement_location": "망울이 구속된 위치 설명",
    "bead_shape": "spherical" | "flattened" | "elongated" | "irregular" | "unknown",
    "bead_distribution": "load_side" | "source_side" | "both" | "unknown",
    "bead_spread": "confined" | "spread" | "scattered" | "unknown",
    "mechanical_constraint_evidence": "물리적 구속의 증거 설명 (망울 형상 포함)",
    "load_side_concentration": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거 (망울 형상 분석 근거 포함)"
}"""


def step1_mechanical_deformation(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 기계적 변형 흔적 분석"""
    if verbose:
        print("\n🔍 [Step 1] 기계적 변형 흔적 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP1_PROMPT, image_data, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        deformation_detected = result.get("mechanical_deformation_detected", False)
        print(f"✅ [Step 1] 완료: 기계적 변형 {'탐지됨' if deformation_detected else '미탐지'}")
    
    return result


def step2_strand_splaying(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 소선 배열의 흐트러짐 분석"""
    if verbose:
        print("\n🎨 [Step 2] 소선 배열의 흐트러짐 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP2_PROMPT, image_data, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        splaying_detected = result.get("strand_splaying_detected", False)
        print(f"✅ [Step 2] 완료: 소선 흐트러짐 {'탐지됨' if splaying_detected else '미탐지'}")
    
    return result


def step3_bead_confinement(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 단락흔의 위치와 구속 분석"""
    if verbose:
        print("\n🔥 [Step 3] 단락흔의 위치와 구속 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP3_PROMPT, image_data, "Step 3", verbose)
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
    deformation_on_non_melted_part = step1_result.get("deformation_on_non_melted_part", False)
    thermal_deformation_excluded = step1_result.get("thermal_deformation_excluded", False)
    causal_relationship = step1_result.get("causal_relationship", False)
    tool_marks_detected = step1_result.get("tool_marks_detected", False)
    strand_splaying_detected = step2_result.get("strand_splaying_detected", False)
    cut_marks_detected = step2_result.get("cut_marks_detected", False)
    crushed_state_detected = step2_result.get("crushed_state_detected", False)
    bead_confinement_detected = step3_result.get("bead_confinement_detected", False)
    bead_shape = step3_result.get("bead_shape", "unknown")
    bead_is_flattened = (bead_shape == "flattened")
    
    base_score = 0
    
    # 기계적 변형이 용융되지 않은 부분에 있고, 열 변형이 배제된 경우만 점수 부여
    if mechanical_deformation_detected and deformation_on_non_melted_part and thermal_deformation_excluded:
        base_score += 20  # 30 -> 20 하향 (단순 변형만으로는 높은 점수 주지 않음)
    elif mechanical_deformation_detected:
        # 용융된 부분의 변형이거나 열 변형 배제가 안 된 경우 점수 감소
        base_score += 10
    
    # 도구 흔적은 강력한 증거
    if tool_marks_detected:
        base_score += 15
    
    # 소선 흐트러짐: 강제 변형 증거가 있을 때만 점수 부여
    if strand_splaying_detected and (cut_marks_detected or crushed_state_detected):
        base_score += 20  # 강제 변형 증거가 있을 때만
    elif strand_splaying_detected:
        base_score += 5  # 단순 흐트러짐만으로는 낮은 점수
    
    # 망울 구속: 납작해진 형태일 때만 높은 점수
    if bead_confinement_detected and bead_is_flattened:
        base_score += 15  # 납작해진 형태면 구속 증거
    elif bead_confinement_detected:
        base_score += 5  # 구형이면 낮은 점수
    
    avg_confidence = (step1_score + step2_score + step3_score) / 3
    base_score += avg_confidence * 0.1
    
    # 강화된 부스트 조건: 기계적 변형 + 보조 증거(소선 흐트러짐 + 망울 구속)가 모두 있어야 높은 점수
    if (mechanical_deformation_detected and deformation_on_non_melted_part and thermal_deformation_excluded 
        and strand_splaying_detected and (cut_marks_detected or crushed_state_detected) 
        and bead_confinement_detected and bead_is_flattened):
        # 핵심 3단계의 평균 신뢰도 계산
        core_avg_confidence = (step1_score + step2_score + step3_score) / 3
        
        # 평균 신뢰도가 높을 때만 가산점 부여
        if core_avg_confidence >= 70:
            boosted_score = base_score * 1.2
            base_score = min(98, max(base_score, int(boosted_score * (core_avg_confidence / 100))))
        elif core_avg_confidence >= 50:
            boosted_score = base_score * 1.1
            base_score = min(85, max(base_score, int(boosted_score * (core_avg_confidence / 100))))
    elif mechanical_deformation_detected and causal_relationship:
        # 단순 변형+위치일치 만으로는 70점 상한선 (오탐지 방어)
        base_score = min(base_score, 70)
    
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
    
    # 기계적 변형이 용융되지 않은 부분에 있고, 열 변형이 배제된 경우만 증거로 인정
    if (mechanical_deformation_detected and 
        step1_result.get("deformation_on_non_melted_part", False) and 
        step1_result.get("thermal_deformation_excluded", False)):
        evidence.append({
            "step": 1,
            "evidence": "기계적 변형 확인 (냉간 변형, 용융되지 않은 부분)",
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
    # 소선 흐트러짐: 강제 변형 증거가 있을 때만 증거로 인정
    if strand_splaying_detected and (step2_result.get("cut_marks_detected", False) or step2_result.get("crushed_state_detected", False)):
        evidence.append({
            "step": 2,
            "evidence": "소선 흐트러짐 확인 (강제 변형 증거: 절단/눌림)",
            "details": step2_result.get("mechanical_force_evidence", "")
        })
    # 망울 구속: 납작해진 형태일 때만 강한 증거로 인정
    if bead_confinement_detected:
        bead_shape = step3_result.get("bead_shape", "unknown")
        if bead_shape == "flattened":
            evidence.append({
                "step": 3,
                "evidence": "망울 구속 확인 (납작해진 형태 - 구속 증거)",
                "details": step3_result.get("mechanical_constraint_evidence", "")
            })
        else:
            evidence.append({
                "step": 3,
                "evidence": "망울 구속 확인 (형상: 구형 - 약한 증거)",
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
        f"- 용융되지 않은 부분의 변형: {'✓ 확인됨' if step1_result.get('deformation_on_non_melted_part', False) else '✗ 미확인'}",
        f"- 열 변형 배제: {'✓ 확인됨' if step1_result.get('thermal_deformation_excluded', False) else '✗ 미확인'}",
        f"- 인과 관계: {'✓ 확인됨' if causal_relationship else '✗ 미확인'}",
        f"- 도구 흔적: {'✓ 확인됨' if tool_marks_detected else '✗ 미확인'}",
        f"- 신뢰도: {step1_result.get('confidence', 0)}%",
        "",
        "**2. 소선 배열의 흐트러짐 분석:**",
        f"- 소선 흐트러짐 탐지: {'✓ 탐지됨' if strand_splaying_detected else '✗ 미탐지'}",
        f"- 흐트러짐 패턴: {step2_result.get('splay_pattern', 'unknown')}",
        f"- 절단 흔적: {'✓ 확인됨' if step2_result.get('cut_marks_detected', False) else '✗ 미확인'}",
        f"- 눌린 상태: {'✓ 확인됨' if step2_result.get('crushed_state_detected', False) else '✗ 미확인'}",
        f"- 소선 배열: {step2_result.get('strand_arrangement', 'unknown')}",
        f"- 신뢰도: {step2_result.get('confidence', 0)}%",
        "",
        "**3. 단락흔의 위치와 구속 분석:**",
        f"- 망울 구속 탐지: {'✓ 탐지됨' if bead_confinement_detected else '✗ 미탐지'}",
        f"- 망울 형상: {step3_result.get('bead_shape', 'unknown')} {'(납작해진 형태 - 구속 증거)' if step3_result.get('bead_shape') == 'flattened' else '(구형 - 일반 단락흔 가능)' if step3_result.get('bead_shape') == 'spherical' else ''}",
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
        print(f"\n{'='*60}\n🔍 압착/기계적 손상 분석 시작\n{'='*60}")
    
    step1_result = step1_mechanical_deformation(image_data, verbose)
    step2_result = step2_strand_splaying(image_data, verbose)
    step3_result = step3_bead_confinement(image_data, verbose)
    
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

