"""
Tracking 전문가 모듈 (Agent_4 기반)
트래킹 판별 전문가 - 3단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from vertexai.generative_models import Part
from src.nodes.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 프롬프트 정의
STEP1_PROMPT = """당신은 전기 표면 방전 및 트래킹 현상 분석 전문가입니다. 다음 이미지에서 수지상 도전로 패턴을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]
1단계: 시각적 요소 추출
- 이미지 전체를 스캔하여 검은색 탄화 흔적의 분포를 관찰하세요.
- 탄화 흔적이 가지처럼 뻗어나가는 패턴을 객관적으로 식별하세요.
- 두 개의 전극(도체, 단자 등) 사이를 연결하는 경로를 찾으세요.

2단계: 특징 서술
- 발견된 패턴을 정확히 서술하세요:
  * 수지상(Dendritic) 패턴: 나뭇가지처럼 뻗어나가는 형태
  * 선형(Linear) 패턴: 직선으로 연결된 형태
  * 복잡한(Complex) 패턴: 여러 경로가 교차하거나 분기하는 형태
- 두 전극을 연결하는 경로가 있는지 확인하세요.
- 패턴의 복잡도(simple, moderate, complex)를 서술하세요.

3단계: 논리적 추론
- 트래킹은 두 전극 사이에 도전로를 형성하는 현상입니다.
- 수지상 패턴은 트래킹의 전형적인 특징입니다.
- 단순한 그을음과 달리 전극을 연결하는 경로가 명확하다면 트래킹 가능성이 높습니다.
- 관찰된 패턴을 종합하여 트래킹 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "dendritic_pattern_detected": true/false,
    "pattern_type": "dendritic" | "linear" | "complex" | "none" | "unknown",
    "pattern_description": "패턴에 대한 상세 설명",
    "electrode_connection": true/false,
    "connection_description": "두 전극을 연결하는 경로 설명",
    "pattern_complexity": "simple" | "moderate" | "complex" | "unknown",
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""

STEP2_PROMPT = """당신은 전기 표면 방전 및 트래킹 현상 분석 전문가입니다. 다음 이미지에서 탄화 흔적의 광택을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]
1단계: 시각적 요소 추출
- 검은색 탄화 흔적의 광학적 특성을 자세히 관찰하세요.
- 반짝임이나 광택이 있는 영역을 객관적으로 식별하세요.
- 조명 반사(Glare)와 탄화물의 광택을 구별하세요.

2단계: 특징 서술
- 발견된 광택을 정확히 서술하세요:
  * 금속성 광택(Metallic Luster)인지
  * 윤기(Shininess)가 있는지
  * 무광택(Matte)인지
- 광택이 탄화된 부분에만 국한되어 있는지 위치를 정확히 서술하세요.
- 조명 반사와 흑연 광택을 구별하는 방법을 서술하세요.

3단계: 논리적 추론
- 일반적인 화재 그을음(Amorphous Carbon)은 무광택(Matte)이며 빛을 흡수합니다.
- 트래킹에 의해 생성된 흑연(Graphite)은 결정 구조로 인해 빛을 정반사(Specular Reflection)하여 반짝입니다.
- 광택이 있다면 트래킹 확률을 매우 높게 설정하세요. 이는 단순 탄화물이 아닌 흑연이 형성되었음을 의미하며, 트래킹의 결정적 증거입니다.
- 관찰된 광택 특성을 종합하여 흑연화 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "luster_detected": true/false,
    "luster_type": "metallic" | "shiny" | "matte" | "none" | "unknown",
    "luster_location": "광택이 관찰된 위치 설명",
    "graphitization_evidence": true/false,
    "glare_distinction": "조명 반사와 흑연 광택의 구별 설명",
    "carbon_type": "graphite" | "amorphous" | "mixed" | "unknown",
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""

STEP3_PROMPT = """당신은 전기 표면 방전 및 트래킹 현상 분석 전문가입니다. 다음 이미지에서 탄화 경로를 따른 표면 침식을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]
1단계: 시각적 요소 추출
- 탄화 경로를 따라 절연체 표면의 손상 상태를 관찰하세요.
- 표면이 움푹 패이거나 굴착된 부분을 객관적으로 식별하세요.
- 탄화물이 표면에 얇게 증착된 것인지, 재료가 변질된 것인지 구별하세요.

2단계: 특징 서술
- 표면 침식을 정확히 서술하세요:
  * 탄화 경로를 따라 절연체 표면이 움푹 패이거나(Eroded) 굴착된 듯한 입체적 손상이 있는지
  * 침식의 깊이(shallow, moderate, deep)를 서술하세요
  * 탄화물이 표면에 얇게 증착된 그을음인지, 재료 표면이 변질되어 형성된 구조적인 트랙인지 구분하세요
- 침식 패턴이 탄화 경로와 일치하는지 서술하세요.

3단계: 논리적 추론
- 트래킹은 표면을 갉아먹으며 진행되므로, 탄화 경로를 따라 재료가 패이거나 소실된 흔적이 남습니다.
- 구조적인 트랙은 단순 그을음과 달리 재료 자체가 변질되어 형성된 것입니다.
- 표면 침식이 탄화 패턴과 일치한다면 트래킹의 강력한 증거입니다.
- 관찰된 침식 패턴을 종합하여 트래킹 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "surface_erosion_detected": true/false,
    "erosion_pattern": "track_following" | "general" | "none" | "unknown",
    "erosion_depth": "shallow" | "moderate" | "deep" | "unknown",
    "carbon_type": "surface_deposit" | "structural_track" | "mixed" | "unknown",
    "erosion_description": "표면 침식에 대한 상세 설명",
    "pattern_match": true/false,
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""


def step1_dendritic_pattern(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 수지상 도전로 패턴 분석"""
    if verbose:
        print("\n🔍 [Step 1] 수지상 도전로 패턴 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP1_PROMPT, image_part, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        pattern_detected = result.get("dendritic_pattern_detected", False)
        print(f"✅ [Step 1] 완료: 수지상 패턴 {'탐지됨' if pattern_detected else '미탐지'}")
    
    return result


def step2_luster_detection(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 광택 감지 분석"""
    if verbose:
        print("\n🎨 [Step 2] 광택 감지 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP2_PROMPT, image_part, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        luster_detected = result.get("luster_detected", False)
        print(f"✅ [Step 2] 완료: 광택 {'탐지됨' if luster_detected else '미탐지'}")
    
    return result


def step3_surface_erosion(image_part: Part, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 표면 침식 분석"""
    if verbose:
        print("\n🔥 [Step 3] 표면 침식 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP3_PROMPT, image_part, "Step 3", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        erosion_detected = result.get("surface_erosion_detected", False)
        print(f"✅ [Step 3] 완료: 표면 침식 {'탐지됨' if erosion_detected else '미탐지'}")
    
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
    
    dendritic_pattern_detected = step1_result.get("dendritic_pattern_detected", False)
    electrode_connection = step1_result.get("electrode_connection", False)
    luster_detected = step2_result.get("luster_detected", False)
    graphitization_evidence = step2_result.get("graphitization_evidence", False)
    surface_erosion_detected = step3_result.get("surface_erosion_detected", False)
    structural_track = step3_result.get("carbon_type") == "structural_track"
    
    base_score = 0
    
    # 핵심 지표 가중치 (광택이 가장 중요)
    if dendritic_pattern_detected:
        base_score += 25
    if electrode_connection:
        base_score += 20
    if luster_detected:
        base_score += 35  # 광택이 트래킹의 결정적 증거
    if graphitization_evidence:
        base_score += 20
    if surface_erosion_detected:
        base_score += 15
    if structural_track:
        base_score += 10
    
    avg_confidence = (step1_score + step2_score + step3_score) / 3
    base_score += avg_confidence * 0.1
    
    # 핵심 3가지가 모두 확인되면 90% 이상 보장
    if dendritic_pattern_detected and luster_detected and surface_erosion_detected:
        base_score = max(base_score, 90)
    
    # 광택만 확인되어도 높은 신뢰도 부여
    if luster_detected and graphitization_evidence:
        base_score = max(base_score, 85)
    
    return min(100, max(0, int(base_score)))


def collect_evidence(
    step1_result: Dict[str, Any],
    step2_result: Dict[str, Any],
    step3_result: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """증거 수집"""
    evidence = []
    
    dendritic_pattern_detected = step1_result.get("dendritic_pattern_detected", False)
    electrode_connection = step1_result.get("electrode_connection", False)
    luster_detected = step2_result.get("luster_detected", False)
    graphitization_evidence = step2_result.get("graphitization_evidence", False)
    surface_erosion_detected = step3_result.get("surface_erosion_detected", False)
    
    if dendritic_pattern_detected:
        evidence.append({
            "step": 1,
            "evidence": "수지상 도전로 패턴 확인",
            "details": step1_result.get("pattern_description", "")
        })
    if electrode_connection:
        evidence.append({
            "step": 1,
            "evidence": "전극 연결 확인",
            "details": step1_result.get("connection_description", "")
        })
    if luster_detected:
        evidence.append({
            "step": 2,
            "evidence": "흑연 광택 확인",
            "details": step2_result.get("luster_location", "")
        })
    if graphitization_evidence:
        evidence.append({
            "step": 2,
            "evidence": "흑연화 증거 확인",
            "details": step2_result.get("glare_distinction", "")
        })
    if surface_erosion_detected:
        evidence.append({
            "step": 3,
            "evidence": "표면 침식 확인",
            "details": step3_result.get("erosion_description", "")
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
    dendritic_pattern_detected = step1_result.get("dendritic_pattern_detected", False)
    electrode_connection = step1_result.get("electrode_connection", False)
    luster_detected = step2_result.get("luster_detected", False)
    graphitization_evidence = step2_result.get("graphitization_evidence", False)
    surface_erosion_detected = step3_result.get("surface_erosion_detected", False)
    
    report_lines = [
        "[Tracking 전문가 리포트]",
        "## 트래킹 (Tracking) 판별 전문가 리포트",
        "",
        "**전문가:** 트래킹 분석 전문가",
        "",
        "**분석 결과 요약:**",
        f"트래킹 판정 신뢰도: {confidence_score}%",
        "",
        "**단계별 분석 결과:**",
        "",
        "**1. 수지상 도전로 패턴 분석:**",
        f"- 수지상 패턴 탐지: {'✓ 탐지됨' if dendritic_pattern_detected else '✗ 미탐지'}",
        f"- 패턴 유형: {step1_result.get('pattern_type', 'unknown')}",
        f"- 전극 연결: {'✓ 확인됨' if electrode_connection else '✗ 미확인'}",
        f"- 패턴 복잡도: {step1_result.get('pattern_complexity', 'unknown')}",
        f"- 신뢰도: {step1_result.get('confidence', 0)}%",
        "",
        "**2. 광택 감지 분석:**",
        f"- 광택 탐지: {'✓ 탐지됨' if luster_detected else '✗ 미탐지'}",
        f"- 광택 유형: {step2_result.get('luster_type', 'unknown')}",
        f"- 흑연화 증거: {'✓ 확인됨' if graphitization_evidence else '✗ 미확인'}",
        f"- 탄소 유형: {step2_result.get('carbon_type', 'unknown')}",
        f"- 신뢰도: {step2_result.get('confidence', 0)}%",
        "",
        "**3. 표면 침식 분석:**",
        f"- 표면 침식 탐지: {'✓ 탐지됨' if surface_erosion_detected else '✗ 미탐지'}",
        f"- 침식 패턴: {step3_result.get('erosion_pattern', 'unknown')}",
        f"- 침식 깊이: {step3_result.get('erosion_depth', 'unknown')}",
        f"- 탄소 유형: {step3_result.get('carbon_type', 'unknown')}",
        f"- 신뢰도: {step3_result.get('confidence', 0)}%",
        "",
        "**증거:**"
    ]
    
    for ev in evidence:
        report_lines.append(f"- Step {ev.get('step')}: {ev.get('evidence')} - {ev.get('details', '')}")
    
    report_lines.extend([
        "",
        "**결론:**",
        f"제공된 데이터를 기반으로 분석한 결과, 트래킹에 의한 단락 가능성이 {'매우 높습니다' if confidence_score >= 80 else '높습니다' if confidence_score >= 60 else '있습니다'} (신뢰도: {confidence_score}%)."
    ])
    
    return "\n".join(report_lines)


def analyze_tracking(payload: List[Any], verbose: bool = False) -> Dict[str, Any]:
    """
    전체 트래킹 분석 실행 함수
    
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
        print(f"\n{'='*60}\n🔍 트래킹 분석 시작\n{'='*60}")
    
    step1_result = step1_dendritic_pattern(image_part, verbose)
    step2_result = step2_luster_detection(image_part, verbose)
    step3_result = step3_surface_erosion(image_part, verbose)
    
    confidence_score = calculate_confidence_score(step1_result, step2_result, step3_result)
    evidence = collect_evidence(step1_result, step2_result, step3_result)
    
    dendritic_pattern_detected = step1_result.get("dendritic_pattern_detected", False)
    electrode_connection = step1_result.get("electrode_connection", False)
    luster_detected = step2_result.get("luster_detected", False)
    graphitization_evidence = step2_result.get("graphitization_evidence", False)
    surface_erosion_detected = step3_result.get("surface_erosion_detected", False)
    
    summary_parts = [f"트래킹 판정 신뢰도: {confidence_score}%"]
    summary_parts.append(
        f"✓ 수지상 패턴 확인: {step1_result.get('pattern_type', 'unknown')}"
        if dendritic_pattern_detected else "✗ 수지상 패턴 미확인"
    )
    summary_parts.append(
        "✓ 전극 연결 확인" if electrode_connection else "✗ 전극 연결 미확인"
    )
    summary_parts.append(
        f"✓ 흑연 광택 확인: {step2_result.get('luster_type', 'unknown')}"
        if luster_detected else "✗ 흑연 광택 미확인"
    )
    summary_parts.append(
        "✓ 흑연화 증거 확인" if graphitization_evidence else "✗ 흑연화 증거 미확인"
    )
    summary_parts.append(
        f"✓ 표면 침식 확인: {step3_result.get('erosion_pattern', 'unknown')}"
        if surface_erosion_detected else "✗ 표면 침식 미확인"
    )
    
    analysis_summary = "\n".join(summary_parts)
    report = generate_report(step1_result, step2_result, step3_result, confidence_score, evidence)
    
    if verbose:
        print(f"✅ 트래킹 분석 완료: 신뢰도 {confidence_score}%")
    
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

