"""
Arbiter 유틸리티 모듈
1차/2차 단락흔 판정 매트릭스, 상충 해결 논리, 증거 위계 적용 함수들
"""
from typing import Dict, Any, List, Optional

# 1차 vs 2차 단락흔 판정 매트릭스
PRIMARY_VS_SECONDARY_MATRIX = {
    "luster": {
        "primary": {"high": 1, "smooth": 1, "metallic": 1, "shiny": 1},
        "secondary": {"low": 1, "rough": 1, "matte": 1, "none": 1}
    },
    "porosity": {
        "primary": {"none": 5, "fine": 5, "dense": 5, "low": 5},
        "secondary": {"high": 5, "porous": 5, "large_pores": 5, "spongy": 5}
    },
    "shape": {
        "primary": {"spherical": 6, "round": 6},
        "secondary": {"irregular": 6, "elliptical": 6, "flowed": 6, "elongated": 6}
    },
    "demarcation": {
        "primary": {"sharp": 1, "clear": 1, "distinct": 1},
        "secondary": {"gradual": 1, "unclear": 1, "diffuse": 1, "blurred": 1}
    },
    "carbonization_location": {
        "primary": {"localized": 3, "focal": 3, "point": 3},
        "secondary": {"widespread": 3, "global": 3, "extensive": 3}
    }
}

# 상충 해결 규칙
CONFLICT_RESOLUTION_RULES = {
    "tracking_vs_aging": {
        "condition": "tracking_luster_detected",
        "priority": "tracking",
        "reason": "흑연 광택은 트래킹의 강력한 증거이므로 절연열화(Aging)보다 우선순위가 높음",
        "weight_adjustment": {"tracking": 1.2, "aging": 0.8}
    },
    "deform_vs_necking": {
        "condition": "deformation_detected",
        "priority": "deform",
        "reason": "압착 흔적이 명확하면 반단선보다 우선하며, 반단선(Necking)은 압착에 의한 2차적 절단으로 해석",
        "weight_adjustment": {"deform": 1.3, "necking": 0.7}
    },
    "shape_vs_surface": {
        "condition": "spherical_and_rough",
        "priority": "surface",
        "reason": "구형이지만 표면이 거칠면 화재 현장의 고온 환경 영향이 더 지배적이므로 2차 단락흔으로 의심",
        "weight_adjustment": {"primary": 0.7, "secondary": 1.3}
    }
}

# 증거 위계
EVIDENCE_HIERARCHY = {
    "morphological_deformation": 3.0,  # 형상학적 변형 (압착)
    "chemical_composition": 2.0,      # 화학적 성분 (아산화동/흑연)
    "general_carbonization": 1.0,     # 일반적 탄화
    "insufficient_evidence": 0.5       # 증거 부족 (페널티)
}

# 판정 불확실성 임계값
# 점수 차이가 이 값 미만이면 "uncertain" 또는 "undetermined" 반환
UNCERTAINTY_THRESHOLD = 2.0

def extract_visual_features(
    expert_analysis_results: dict,
    expert_evidence: dict
) -> Dict[str, Any]:
    """
    전문가 분석 결과에서 시각적 특징 추출
    
    실제 반환 구조에 맞게 수정:
    - expert_analysis_results["contact"] = {"multi_hotspot_results": [...], "final_verdict_result": {...}}
    - 각 결과에서 visual_description 텍스트를 분석하여 특징 추출
    
    Args:
        expert_analysis_results: 각 전문가의 분석 결과
        expert_evidence: 각 전문가의 증거 리스트
        
    Returns:
        추출된 시각적 특징 딕셔너리
    """
    features = {
        "luster": None,
        "porosity": None,
        "shape": None,
        "demarcation": None,
        "carbonization_location": None,
        "surface_texture": None
    }
    
    def extract_text_from_results(expert_name: str) -> str:
        """전문가 결과에서 모든 텍스트를 추출"""
        expert_data = expert_analysis_results.get(expert_name, {})
        if not expert_data:
            return ""
        
        texts = []
        
        # final_verdict_result에서 visual_description 추출
        final_result = expert_data.get("final_verdict_result", {})
        if final_result:
            visual_desc = final_result.get("visual_description", "")
            if visual_desc:
                texts.append(visual_desc.lower())
        
        # multi_hotspot_results에서 visual_description 추출
        multi_results = expert_data.get("multi_hotspot_results", [])
        for result in multi_results:
            specialist_result = result.get("specialist_result", {})
            if specialist_result:
                visual_desc = specialist_result.get("visual_description", "")
                if visual_desc:
                    texts.append(visual_desc.lower())
        
        return " ".join(texts)
    
    # Tracking 전문가에서 광택 정보 추출 (비활성화되어 있지만 코드 유지)
    tracking_results = expert_analysis_results.get("tracking", {})
    if tracking_results:
        # 기존 구조 지원 (향후 활성화 시)
        step2 = tracking_results.get("step2", {})
        if step2:
            luster_type = step2.get("luster_type", "unknown")
            luster_detected = step2.get("luster_detected", False)
            graphitization = step2.get("graphitization_evidence", False)
            
            if luster_detected and graphitization:
                features["luster"] = "high" if luster_type in ["metallic", "shiny"] else "low"
            elif luster_detected:
                features["luster"] = "high" if luster_type in ["metallic", "shiny"] else "low"
            else:
                features["luster"] = "matte"
    
    # Aging 전문가에서 기공 및 탄화 위치 정보 추출 (비활성화되어 있지만 코드 유지)
    aging_results = expert_analysis_results.get("aging", {})
    if aging_results:
        # 기존 구조 지원 (향후 활성화 시)
        step1 = aging_results.get("step1", {})
        step3 = aging_results.get("step3", {})
        if step1:
            direction = step1.get("carbonization_direction", "unknown")
            if direction == "internal_to_external":
                features["carbonization_location"] = "localized"
        if step3:
            global_aging = step3.get("global_aging_detected", False)
            if global_aging:
                features["carbonization_location"] = "widespread"
    
    # Deform 전문가에서 형상 정보 추출
    deform_text = extract_text_from_results("deform")
    if deform_text:
        # 비드 형상 키워드 검색
        if any(keyword in deform_text for keyword in ["spherical", "구형", "round", "원형", "bead"]):
            features["shape"] = "spherical"
        elif any(keyword in deform_text for keyword in ["elongated", "elongation", "늘어남", "irregular", "불규칙"]):
            features["shape"] = "irregular"
        elif any(keyword in deform_text for keyword in ["taper", "tapering", "테이퍼", "가늘어짐"]):
            features["shape"] = "irregular"  # Tapering은 irregular로 분류
    
    # Contact 전문가에서 표면 질감 정보 추출
    contact_text = extract_text_from_results("contact")
    if contact_text:
        # 표면 질감 키워드 검색
        if any(keyword in contact_text for keyword in ["smooth", "매끄러운", "glossy", "광택"]):
            features["surface_texture"] = "smooth"
        elif any(keyword in contact_text for keyword in ["rough", "거친", "roughness", "거칠기"]):
            features["surface_texture"] = "rough"
        elif any(keyword in contact_text for keyword in ["porous", "다공성", "spongy", "스펀지"]):
            features["surface_texture"] = "rough"
            features["porosity"] = "high"
    
    # Necking 전문가에서 형상 정보 추출 (Deform과 유사하지만 별도 처리)
    necking_text = extract_text_from_results("necking")
    if necking_text and not features["shape"]:
        # Necking은 일반적으로 irregular 형상을 가짐
        if any(keyword in necking_text for keyword in ["necking", "반단선", "taper", "tapering", "가늘어짐"]):
            features["shape"] = "irregular"
    
    # Tracking 전문가에서 경계 정보 추출 (비활성화되어 있지만 코드 유지)
    if tracking_results:
        step1 = tracking_results.get("step1", {})
        if step1:
            complexity = step1.get("pattern_complexity", "unknown")
            if complexity == "simple":
                features["demarcation"] = "sharp"
            elif complexity in ["moderate", "complex"]:
                features["demarcation"] = "gradual"
    
    return features

def calculate_primary_secondary_score(
    visual_features: dict,
    matrix: dict = None,
    uncertainty_threshold: float = None
) -> Dict[str, Any]:
    """
    1차/2차 단락흔 점수 계산 (불확실성 로직 강화)
    
    Args:
        visual_features: 추출된 시각적 특징
        matrix: 판정 매트릭스 (기본값: PRIMARY_VS_SECONDARY_MATRIX)
        uncertainty_threshold: 점수 차이 임계값 (기본값: UNCERTAINTY_THRESHOLD)
                               이 값 미만이면 "uncertain" 반환
        
    Returns:
        {
            "primary_score": int,
            "secondary_score": int,
            "determination": str ("primary" | "secondary" | "uncertain" | "undetermined"),
            "score_difference": float,
            "observed_count": int  # 관측된 특징 개수 (디버깅용)
        }
    """
    if matrix is None:
        matrix = PRIMARY_VS_SECONDARY_MATRIX
    
    if uncertainty_threshold is None:
        uncertainty_threshold = UNCERTAINTY_THRESHOLD
    
    primary_score = 0
    secondary_score = 0
    observed_features_count = 0  # 관측된 특징 개수
    
    # 각 특징별 점수 계산
    for feature_name, feature_value in visual_features.items():
        if feature_value is None:
            continue
        
        feature_matrix = matrix.get(feature_name)
        if not feature_matrix:
            continue
        
        observed_features_count += 1  # 관측 카운트 증가
        
        # 1차 단락흔 점수
        primary_indicators = feature_matrix.get("primary", {})
        for indicator, weight in primary_indicators.items():
            if indicator.lower() in str(feature_value).lower():
                primary_score += weight
                break
        
        # 2차 단락흔 점수
        secondary_indicators = feature_matrix.get("secondary", {})
        for indicator, weight in secondary_indicators.items():
            if indicator.lower() in str(feature_value).lower():
                secondary_score += weight
                break
    
    # 점수 차이 계산
    score_diff = abs(primary_score - secondary_score)
    
    # 판정 로직 고도화
    if observed_features_count == 0:
        # 관측된 특징이 하나도 없음
        determination = "undetermined"
    elif score_diff <= uncertainty_threshold:
        # 점수 차이가 미미함 (판단 보류)
        determination = "uncertain"
    elif primary_score > secondary_score:
        determination = "primary"
    elif secondary_score > primary_score:
        determination = "secondary"
    else:
        # 점수가 동일한 경우
        determination = "uncertain"
    
    return {
        "primary_score": primary_score,
        "secondary_score": secondary_score,
        "determination": determination,
        "score_difference": score_diff,
        "observed_count": observed_features_count  # 디버깅용
    }

def resolve_conflict_tracking_vs_aging(
    tracking_result: dict,
    aging_result: dict,
    tracking_score: float,
    aging_score: float
) -> Dict[str, Any]:
    """
    Case A: 트래킹 vs 절연열화(Aging) 상충 해결
    
    Args:
        tracking_result: Tracking 전문가 분석 결과
        aging_result: Aging 전문가 분석 결과
        tracking_score: Tracking 전문가 신뢰도 점수
        aging_score: Aging 전문가 신뢰도 점수
        
    Returns:
        {"resolved": bool, "priority": str, "adjusted_scores": dict, "reason": str}
    """
    tracking_step2 = tracking_result.get("step2", {})
    luster_detected = tracking_step2.get("luster_detected", False)
    graphitization = tracking_step2.get("graphitization_evidence", False)
    
    if luster_detected and graphitization:
        # 흑연 광택이 있으면 트래킹 우선
        adjusted_tracking = tracking_score * 1.2
        adjusted_aging = aging_score * 0.8
        
        return {
            "resolved": True,
            "priority": "tracking",
            "adjusted_scores": {
                "tracking": adjusted_tracking,
                "aging": adjusted_aging
            },
            "reason": "흑연 광택은 트래킹의 강력한 증거이므로 절연열화(Aging)보다 우선순위가 높습니다."
        }
    
    return {
        "resolved": False,
        "priority": None,
        "adjusted_scores": {
            "tracking": tracking_score,
            "aging": aging_score
        },
        "reason": "상충 없음"
    }

def resolve_conflict_deform_vs_necking(
    deform_result: dict,
    necking_result: dict,
    deform_score: float,
    necking_score: float
) -> Dict[str, Any]:
    """
    Case B: 압착 vs 반단선(Necking) 상충 해결
    
    실제 반환 구조에 맞게 수정:
    - deform_result = {"multi_hotspot_results": [...], "final_verdict_result": {...}}
    - final_verdict_result에서 conclusion과 visual_description을 확인
    
    Args:
        deform_result: Deform 전문가 분석 결과
        necking_result: Necking 전문가 분석 결과
        deform_score: Deform 전문가 신뢰도 점수
        necking_score: Necking 전문가 신뢰도 점수
        
    Returns:
        {"resolved": bool, "priority": str, "adjusted_scores": dict, "reason": str}
    """
    def extract_conclusion_and_text(expert_data: dict) -> tuple:
        """전문가 결과에서 결론과 텍스트 추출"""
        if not expert_data:
            return None, ""
        
        # final_verdict_result에서 추출
        final_result = expert_data.get("final_verdict_result", {})
        conclusion = final_result.get("conclusion", "")
        visual_desc = final_result.get("visual_description", "")
        
        # multi_hotspot_results에서도 추출
        multi_results = expert_data.get("multi_hotspot_results", [])
        texts = [visual_desc.lower()] if visual_desc else []
        for result in multi_results:
            specialist_result = result.get("specialist_result", {})
            if specialist_result:
                desc = specialist_result.get("visual_description", "")
                if desc:
                    texts.append(desc.lower())
        
        return conclusion, " ".join(texts)
    
    deform_conclusion, deform_text = extract_conclusion_and_text(deform_result)
    necking_conclusion, necking_text = extract_conclusion_and_text(necking_result)
    
    # 압착 흔적이 명확한지 확인
    deformation_keywords = ["압착", "압축", "deform", "deformation", "compression", "기계적"]
    deformation_detected = any(keyword in deform_text for keyword in deformation_keywords) or \
                          (deform_conclusion and "압착" in str(deform_conclusion))
    
    # 인과관계 확인 (압착이 원인인지)
    causal_keywords = ["원인", "cause", "causal", "직접적"]
    causal_relationship = any(keyword in deform_text for keyword in causal_keywords)
    
    if deformation_detected and (causal_relationship or deform_score > necking_score):
        # 압착 흔적이 명확하면 압착 우선
        adjusted_deform = deform_score * 1.3
        adjusted_necking = necking_score * 0.7
        
        return {
            "resolved": True,
            "priority": "deform",
            "adjusted_scores": {
                "deform": adjusted_deform,
                "necking": adjusted_necking
            },
            "reason": "압착 흔적이 명확하면 반단선보다 우선하며, 반단선은 압착에 의한 2차적 절단으로 해석됩니다."
        }
    
    return {
        "resolved": False,
        "priority": None,
        "adjusted_scores": {
            "deform": deform_score,
            "necking": necking_score
        },
        "reason": "상충 없음"
    }

def resolve_conflict_shape_vs_surface(
    shape: str,
    surface_texture: str,
    primary_score: float,
    secondary_score: float
) -> Dict[str, Any]:
    """
    Case C: 형상 vs 표면 상충 해결
    
    Args:
        shape: 형상 특징 ("spherical", "irregular" 등)
        surface_texture: 표면 질감 ("smooth", "rough" 등)
        primary_score: 1차 단락흔 점수
        secondary_score: 2차 단락흔 점수
        
    Returns:
        {"resolved": bool, "priority": str, "adjusted_scores": dict, "reason": str}
    """
    if shape == "spherical" and surface_texture == "rough":
        # 구형이지만 거칠면 2차 단락흔 의심
        adjusted_primary = primary_score * 0.7
        adjusted_secondary = secondary_score * 1.3
        
        return {
            "resolved": True,
            "priority": "secondary",
            "adjusted_scores": {
                "primary": adjusted_primary,
                "secondary": adjusted_secondary
            },
            "reason": "구형이지만 표면이 거칠면 화재 현장의 고온 환경 영향이 더 지배적이므로 2차 단락흔으로 의심됩니다."
        }
    
    return {
        "resolved": False,
        "priority": None,
        "adjusted_scores": {
            "primary": primary_score,
            "secondary": secondary_score
        },
        "reason": "상충 없음"
    }

def apply_conflict_resolution(
    expert_analysis_results: dict,
    expert_confidence_scores: dict,
    expert_evidence: dict = None
) -> Dict[str, Any]:
    """
    전체 상충 해결 적용
    
    Args:
        expert_analysis_results: 각 전문가의 분석 결과
        expert_confidence_scores: 각 전문가의 신뢰도 점수
        expert_evidence: 각 전문가의 증거 리스트 (Case C용, 선택적)
        
    Returns:
        {"adjusted_scores": dict, "conflicts": list, "resolutions": list}
    """
    adjusted_scores = expert_confidence_scores.copy()
    conflicts = []
    resolutions = []
    
    # Case A: 트래킹 vs 절연열화(Aging)
    tracking_result = expert_analysis_results.get("tracking", {})
    aging_result = expert_analysis_results.get("aging", {})
    tracking_score = expert_confidence_scores.get("tracking", 0)
    aging_score = expert_confidence_scores.get("aging", 0)
    
    if tracking_result and aging_result:
        conflict_a = resolve_conflict_tracking_vs_aging(
            tracking_result, aging_result, tracking_score, aging_score
        )
        if conflict_a["resolved"]:
            conflicts.append("tracking_vs_aging")
            resolutions.append(conflict_a)
            adjusted_scores.update(conflict_a["adjusted_scores"])
    
    # Case B: 압착 vs 반단선(Necking)
    deform_result = expert_analysis_results.get("deform", {})
    necking_result = expert_analysis_results.get("necking", {})
    deform_score = expert_confidence_scores.get("deform", 0)
    necking_score = expert_confidence_scores.get("necking", 0)
    
    if deform_result and necking_result:
        conflict_b = resolve_conflict_deform_vs_necking(
            deform_result, necking_result,
            deform_score, necking_score
        )
        if conflict_b["resolved"]:
            conflicts.append("deform_vs_necking")
            resolutions.append(conflict_b)
            adjusted_scores.update(conflict_b["adjusted_scores"])
    
    # Case C: 형상 vs 표면 상충 해결
    if expert_evidence is not None:
        visual_features = extract_visual_features(expert_analysis_results, expert_evidence)
        shape = visual_features.get("shape")
        surface_texture = visual_features.get("surface_texture")
        
        if shape and surface_texture:
            # 1차/2차 단락흔 점수 계산
            primary_secondary_result = calculate_primary_secondary_score(visual_features)
            primary_score = primary_secondary_result.get("primary_score", 0)
            secondary_score = primary_secondary_result.get("secondary_score", 0)
            
            conflict_c = resolve_conflict_shape_vs_surface(
                shape, surface_texture, primary_score, secondary_score
            )
            if conflict_c["resolved"]:
                conflicts.append("shape_vs_surface")
                resolutions.append(conflict_c)
                # Case C는 전문가 신뢰도 점수 조정이 아니라 1차/2차 판정 점수 조정이므로
                # adjusted_scores 업데이트는 하지 않음 (정보만 기록)
    
    return {
        "adjusted_scores": adjusted_scores,
        "conflicts": conflicts,
        "resolutions": resolutions
    }

def apply_evidence_hierarchy(
    expert_scores: dict,
    expert_evidence: dict,
    hierarchy: dict = None
) -> Dict[str, Any]:
    """
    증거 위계 적용
    
    Args:
        expert_scores: 각 전문가의 신뢰도 점수
        expert_evidence: 각 전문가의 증거 리스트
        hierarchy: 증거 위계 딕셔너리 (기본값: EVIDENCE_HIERARCHY)
        
    Returns:
        {"weighted_scores": dict, "evidence_types": dict}
    """
    if hierarchy is None:
        hierarchy = EVIDENCE_HIERARCHY
    
    weighted_scores = {}
    evidence_types = {}
    
    # 각 전문가별 증거 유형 분류
    for expert_name, evidence_list in expert_evidence.items():
        base_score = expert_scores.get(expert_name, 0)
        
        if not evidence_list:
            # 증거가 없으면 신뢰도를 대폭 깎아야 함 (페널티 적용)
            weighted_scores[expert_name] = base_score * 0.5  # 페널티 적용
            evidence_types[expert_name] = "insufficient_evidence"
        else:
            # 증거 유형 판별
            evidence_type = "general_carbonization"  # 기본값
            
            for ev in evidence_list:
                evidence_text = ev.get("evidence", "").lower()
                
                # 형상학적 변형 (압착, 기계적 손상)
                if any(keyword in evidence_text for keyword in ["압착", "기계적", "변형", "손상", "도구"]):
                    evidence_type = "morphological_deformation"
                    break
                
                # 화학적 성분 (아산화동, 흑연)
                if any(keyword in evidence_text for keyword in ["아산화동", "흑연", "광택", "산화"]):
                    evidence_type = "chemical_composition"
                    break
            
            evidence_types[expert_name] = evidence_type
            
            # 가중치 적용
            weight = hierarchy.get(evidence_type, 1.0)
            weighted_scores[expert_name] = base_score * weight
    
    return {
        "weighted_scores": weighted_scores,
        "evidence_types": evidence_types
    }

def determine_dominant_expert(
    weighted_scores: Dict[str, float],
    absolute_threshold: float = 70.0,
    margin_threshold: float = 20.0
) -> Dict[str, Any]:
    """
    압도적 1위 전문가(Dominant Expert) 선정 로직 (Winner-Takes-All)
    
    Args:
        weighted_scores: 증거 위계가 적용된 전문가별 점수
        absolute_threshold: 1위가 되기 위한 최소 점수 (예: 70점)
        margin_threshold: 2위와의 최소 격차 (예: 20점)
        
    Returns:
        {
            "dominant_expert": str | None,
            "max_score": float,
            "second_score": float,
            "margin": float,
            "is_determined": bool
        }
    """
    if not weighted_scores:
        return {
            "dominant_expert": None,
            "max_score": 0,
            "second_score": 0,
            "margin": 0,
            "is_determined": False
        }
    
    # 점수 내림차순 정렬
    sorted_experts = sorted(weighted_scores.items(), key=lambda x: x[1], reverse=True)
    
    top_expert, top_score = sorted_experts[0]
    
    if len(sorted_experts) > 1:
        second_expert, second_score = sorted_experts[1]
        margin = top_score - second_score
    else:
        second_score = 0
        margin = top_score  # 전문가가 1명뿐인 경우
        
    # 판정 로직
    # 1. 1등 점수가 절대 기준을 넘는가?
    # 2. 2등과의 격차가 충분한가? (독보적인가?)
    is_determined = (top_score >= absolute_threshold) and (margin >= margin_threshold)
    
    return {
        "dominant_expert": top_expert if is_determined else None,
        "max_score": top_score,
        "second_score": second_score,
        "margin": margin,
        "is_determined": is_determined
    }
