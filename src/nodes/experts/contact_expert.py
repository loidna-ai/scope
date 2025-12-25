"""
Contact 전문가 모듈 (Agent_1 기반)
접촉불량 판별 전문가 - 4단계 순차 분석
"""
from typing import Dict, Any, List, Optional
from src.nodes.experts.expert_utils import (
    extract_image_from_payload,
    call_gemini_vision,
    parse_json_response
)

# 프롬프트 정의
STEP1_PROMPT = """당신은 전기화재 감식 전문가입니다. 다음 이미지를 분석하여 용융흔이 발생한 위치를 식별하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 이미지 품질 평가 및 시각적 요소 추출
- 먼저 이미지의 해상도, 선명도, 조명 상태를 평가하세요.
- 이미지가 흐리거나 해상도가 낮으면, 미세 특징 식별이 제한될 수 있음을 명시하세요.
- 이미지 전체를 스캔하여 용융흔(용융망울, 변색된 금속, 탄화 흔적 등)이 보이는 모든 위치를 식별하세요.
- 각 위치의 시각적 특징을 객관적으로 기록하세요 (색상, 형태, 크기, 위치 등).

2단계: 특징 서술
- 식별된 용융흔의 위치가 다음 중 어디에 해당하는지 정확히 서술하세요:
  * 전선의 끝단(Terminal): 전선이 끝나는 지점
  * 콘센트 플러그의 칼날(Blade): 플러그의 금속 접촉부
  * 나사 체결 부위(Screw connection): 나사로 고정된 접속부
  * 전선 접속점(Splicing point): 두 전선이 연결된 지점
  * 전선의 중간 부분(Mid-span): 전선의 중간 구간
- 각 위치의 구조적 특징과 용융흔의 관계를 상세히 서술하세요.

3단계: 논리적 추론
- 접속점(끝단, 칼날, 나사, 접속점)에서 용융흔이 발견된 경우, 접촉불량 가능성을 높게 평가하세요.
- 전선 중간 부분에서만 용융흔이 발견된 경우, 접촉불량보다는 다른 원인(과부하, 절연파괴 등)을 고려하세요.
- 위치와 용융흔의 인과관계를 논리적으로 설명하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "is_connection_point": true/false,
    "location_type": "terminal" | "blade" | "screw" | "splicing" | "mid_span" | "unknown",
    "location_description": "위치에 대한 상세 설명",
    "image_quality": "high" | "medium" | "low" | "unknown",
    "image_quality_reason": "이미지 품질 평가 근거 (선명도, 해상도, 조명 등)",
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""

STEP2_PROMPT = """당신은 전기화재 감식 전문가입니다. 다음 이미지에서 아산화동(Cu₂O)을 의심할 수 있는 색상 패턴을 관찰하세요.

[중요 제약 조건]
- 일반 RGB 카메라 이미지로는 화학적 성분을 확정할 수 없습니다.
- 색상만으로는 아산화동, 산화동(CuO), 다른 산화물, 열변색 등을 구별할 수 없습니다.
- 따라서 "아산화동 탐지"가 아닌 "아산화동을 의심할 수 있는 색상 패턴 관찰"만 수행하세요.
- 화학적 성분 분석은 육안 관찰로 불가능하므로, 색상적 특징만 기술하고 확정하지 말 것.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 금속 표면(구리선, 단자, 플러그 등)의 모든 색상 영역을 식별하세요.
- 검은색 그을음(Soot)과 구별되는 색상 영역을 찾으세요.
- 각 색상 영역의 위치, 크기, 분포를 객관적으로 기록하세요.

2단계: 특징 서술
- 발견된 색상이 다음 중 어떤 계열에 해당하는지 정확히 서술하세요:
  * 붉은색(Red): 따뜻한 빨간 톤
  * 주황색(Orange): 빨강과 노랑의 중간 톤
  * 적갈색(Russet): 갈색이 섞인 붉은 톤
- 이러한 색상이 금속 용융부 주변이나 단자 표면에 부착되어 있는지 위치를 정확히 서술하세요.
- 녹색 녹(Green rust)이 있는 경우, 그 위치와 색상 특성(채도, 명도)을 구별하여 서술하세요.

3단계: 논리적 추론
- 붉은/주황/적갈색 산화물이 금속 접속부에 집중되어 있다면, 이는 아산화동(Cu₂O)을 의심할 수 있는 색상 패턴일 수 있습니다.
- 다만, 화학적 성분 확정은 불가능하므로 "의심 가능성"으로만 기술하세요.
- 이러한 색상 패턴은 접촉불량으로 인한 국부적 과열의 가능한 지표일 수 있습니다.
- 녹색 녹은 화재 진압 시 물에 의한 2차 부식으로, 아산화동과는 다른 메커니즘입니다.
- 색상의 위치, 분포, 톤을 종합하여 아산화동을 의심할 수 있는 색상 패턴의 존재 여부를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "suspicious_color_pattern_detected": true/false,
    "color_analysis": {
        "red_tone_present": true/false,
        "orange_tone_present": true/false,
        "russet_tone_present": true/false,
        "dominant_colors": ["색상1", "색상2", ...]
    },
    "location_of_coloration": "색상이 발견된 위치 설명",
    "cuprous_oxide_suspicion_level": "high" | "medium" | "low" | "none",
    "confidence": 0-100,
    "reasoning": "판단 근거 및 화학적 성분 확정 불가능성 명시"
}"""

STEP3_PROMPT = """당신은 전기화재 감식 전문가입니다. 다음 이미지에서 열적 구배(Thermal Gradient) 패턴을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 전선 피복의 탄화/소실 패턴을 전체적으로 관찰하세요.
- 탄화 정도가 다른 영역들을 식별하고, 각 영역의 위치와 탄화 강도를 객관적으로 기록하세요.
- 수지(Resin)가 흘러내린 흔적이 있다면 그 방향과 위치를 식별하세요.

2단계: 특징 서술
- 접속부에서 멀어질수록 탄화 정도가 어떻게 변화하는지 구체적으로 서술하세요.
- V자형, 선형, 또는 균일한 패턴 중 어떤 형태인지 정확히 서술하세요.
- 수지 흐름의 방향이 중력 방향과 일치하는지, 그리고 접속 단자 위치와의 관계를 서술하세요.
- 열 손상의 중심점(가장 심하게 탄화된 지점)을 정확히 위치시켜 서술하세요.

3단계: 논리적 추론
- 접속부에서 시작하여 전선을 따라 멀어질수록 탄화가 약해지는 패턴은, 접속점에서 열이 발생하여 전도(Conduction)로 전파되었음을 시사합니다.
- 이는 접촉불량으로 인한 국부적 과열의 전형적 특징입니다.
- 외부 화재의 경우 전선 전체가 균일하게 가열되므로, 이러한 구배 패턴이 나타나지 않습니다.
- 수지 흐름이 접속부 발열과 일치한다면, 접촉불량의 추가 증거가 됩니다.
- 관찰된 패턴을 종합하여 열적 구배의 존재 여부와 그 의미를 논리적으로 판단하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "thermal_gradient_detected": true/false,
    "gradient_pattern": "V_shape" | "linear" | "none" | "unknown",
    "heat_source_location": "열원의 위치 설명",
    "heat_propagation_direction": "열 전파 방향 설명",
    "resin_flow_detected": true/false,
    "resin_flow_direction": "수지 흐름 방향 (중력 방향과 일치하는지)",
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""

STEP4_PROMPT = """당신은 전기화재 감식 전문가입니다. 다음 이미지에서 금속 표면의 전기적 부식 흔적을 분석하세요.

[중요] 먼저 분석 과정을 단계별로 자세히 설명한 후, 마지막에 JSON 형식으로 응답하세요. 각 단계에서 무엇을 관찰하고 어떻게 판단하는지 명확히 서술하세요.

[주의 사항]
- **빛 반사 오인 방지**: 빛 반사에 의한 하이라이트(Highlight)나 스펙큘러 리플렉션(Specular Reflection)을 금속이 파인 구멍(Pitting)으로 오인하지 마세요.
- **표면 거칠기 구분**: 표면의 거칠기가 용융 후 굳은 수축(Shrinkage)인지, 전기적 아크에 의한 침식(Erosion)인지 구분하기 위해 주변 그을음과의 관계를 살피세요.
- **해상도 제약**: 미세 기공(Pitting)이나 마이크로 글로뷸(Micro-globule) 같은 특징은 고해상도 이미지가 아니면 식별이 불가능할 수 있습니다. 이미지가 흐리거나 해상도가 낮으면 신뢰도를 낮게 설정하세요.

[단계별 분석 프로세스 (Chain of Thought)]

1단계: 시각적 요소 추출
- 단자, 플러그 핀, 접속부 등 금속 표면을 확대하여 관찰하세요.
- 표면의 질감, 요철, 구멍, 변색 등 모든 시각적 특징을 객관적으로 식별하세요.
- 매끄러운 부분과 거친 부분을 구분하여 기록하세요.
- **빛 반사와 실제 구멍을 구분**: 하이라이트는 위치가 변할 수 있지만, 실제 구멍은 고정된 위치에 있습니다.
- **주변 그을음과의 관계 확인**: 전기적 부식은 그을음과 함께 나타나는 경우가 많습니다.

2단계: 특징 서술
- 발견된 표면 특징을 정확히 서술하세요:
  * 곰보 자국(Pitting): 작은 구멍이나 움푹 패인 자국 (빛 반사와 구별 필요)
  * 요철(Undulation): 울퉁불퉁한 표면
  * 거친 질감: 삭은 듯하거나 거칠게 마모된 표면
- 이러한 특징이 어느 위치에 집중되어 있는지 정확히 서술하세요.
- 표면이 매끄러운 용융인지, 거친 침식인지 구별하여 서술하세요.
- **수축(Shrinkage) vs 침식(Erosion) 구분**: 수축은 용융 후 냉각 과정에서 발생하며, 침식은 전기적 아크에 의한 것입니다.

3단계: 논리적 추론
- 거친 표면, 곰보 자국, 요철은 지속적인 스파크와 아크 방전으로 인한 전기적 부식(Electrical Erosion)의 특징입니다.
- 매끄러운 용융은 단순 과열에 의한 것이며, 거친 침식은 반복적인 전기 방전에 의한 것입니다.
- 접촉불량은 불안정한 접촉으로 인해 반복적인 스파크와 아크를 발생시켜, 이러한 전기적 부식을 유발합니다.
- 관찰된 표면 특징의 위치, 분포, 정도를 종합하여 전기적 부식 여부를 논리적으로 판단하세요.
- **이미지 품질 고려**: 이미지가 흐리거나 해상도가 낮아 미세 특징을 식별하기 어렵다면, 신뢰도를 낮게 설정하세요.

[출력 형식]
다음 JSON 형식으로 응답하세요:
{
    "electrical_erosion_detected": true/false,
    "surface_texture": "smooth" | "rough" | "pitted" | "unknown",
    "pitting_detected": true/false,
    "pitting_description": "곰보 자국에 대한 설명",
    "erosion_pattern": "침식 패턴 설명",
    "confidence": 0-100,
    "reasoning": "판단 근거"
}"""


def step1_location_context(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 1: 위치적 맥락 확인"""
    if verbose:
        print("\n🔍 [Step 1] 위치적 맥락 확인 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP1_PROMPT, image_data, "Step 1", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        print(f"✅ [Step 1] 완료: {result.get('location_type', 'unknown')}")
    
    return result


def step2_spectral_analysis(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 2: 색채 스펙트럼 분석 (아산화동 의심 색상 패턴 관찰)"""
    if verbose:
        print("\n🎨 [Step 2] 색채 스펙트럼 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP2_PROMPT, image_data, "Step 2", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        # 하위 호환성을 위해 두 필드 모두 확인
        detected = result.get("suspicious_color_pattern_detected", False) or result.get("cuprous_oxide_detected", False)
        suspicion_level = result.get("cuprous_oxide_suspicion_level", "none")
        print(f"✅ [Step 2] 완료: 아산화동 의심 색상 패턴 {'관찰됨' if detected else '미관찰'} (의심도: {suspicion_level})")
    
    return result


def step3_thermal_gradient(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 3: 열적 구배 분석"""
    if verbose:
        print("\n🔥 [Step 3] 열적 구배 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP3_PROMPT, image_data, "Step 3", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        gradient_detected = result.get("thermal_gradient_detected", False)
        print(f"✅ [Step 3] 완료: 열적 구배 {'탐지됨' if gradient_detected else '미탐지'}")
    
    return result


def step4_surface_analysis(image_data: bytes, verbose: bool = False) -> Dict[str, Any]:
    """Step 4: 금속 표면 상태 분석"""
    if verbose:
        print("\n🔬 [Step 4] 금속 표면 상태 분석 시작...")
    
    response_text, thinking_info = call_gemini_vision(STEP4_PROMPT, image_data, "Step 4", verbose)
    result = parse_json_response(response_text)
    
    if thinking_info:
        result["thinking_process"] = thinking_info
    
    if verbose:
        erosion_detected = result.get("electrical_erosion_detected", False)
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

