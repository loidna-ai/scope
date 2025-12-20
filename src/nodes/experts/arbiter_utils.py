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
    "tracking_vs_dielectric": {
        "condition": "tracking_luster_detected",
        "priority": "tracking",
        "reason": "흑연 광택은 트래킹의 강력한 증거이므로 절연열화보다 우선순위가 높음",
        "weight_adjustment": {"tracking": 1.2, "dielectric": 0.8}
    },
    "mechanical_vs_strand_fracture": {
        "condition": "mechanical_deformation_detected",
        "priority": "mechanical",
        "reason": "압착 흔적이 명확하면 반단선보다 우선하며, 반단선은 압착에 의한 2차적 절단으로 해석",
        "weight_adjustment": {"mechanical": 1.3, "strand_fracture": 0.7}
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
    "general_carbonization": 1.0      # 일반적 탄화
}


def extract_visual_features(
    expert_analysis_results: dict,
    expert_evidence: dict
) -> dict:
    """
    전문가 분석 결과에서 시각적 특징 추출
    
    Args:
        expert_analysis_results: 각 전문가의 단계별 분석 결과
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
    
    # Tracking 전문가에서 광택 정보 추출
    tracking_results = expert_analysis_results.get("tracking", {})
    if tracking_results:
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
    
    # Dielectric 전문가에서 기공 정보 추출
    dielectric_results = expert_analysis_results.get("dielectric", {})
    if dielectric_results:
        step2 = dielectric_results.get("step2", {})
        if step2:
            spongy = step2.get("spongy_texture_detected", False)
            porous = step2.get("porous_structure_detected", False)
            
            if spongy or porous:
                features["porosity"] = "high"
            else:
                features["porosity"] = "low"
        
        # 탄화 위치 정보 추출
        step1 = dielectric_results.get("step1", {})
        step3 = dielectric_results.get("step3", {})
        if step1:
            direction = step1.get("carbonization_direction", "unknown")
            if direction == "internal_to_external":
                features["carbonization_location"] = "localized"
        if step3:
            global_aging = step3.get("global_aging_detected", False)
            if global_aging:
                features["carbonization_location"] = "widespread"
    
    # Mechanical 전문가에서 형상 정보 추출
    mechanical_results = expert_analysis_results.get("mechanical", {})
    if mechanical_results:
        step2 = mechanical_results.get("step2", {})
        if step2:
            bead_shape = step2.get("bead_shape", "unknown")
            if bead_shape == "spherical":
                features["shape"] = "spherical"
            elif bead_shape in ["elongated", "irregular"]:
                features["shape"] = "irregular"
    
    # Contact 전문가에서 표면 질감 정보 추출
    contact_results = expert_analysis_results.get("contact", {})
    if contact_results:
        step4 = contact_results.get("step4", {})
        if step4:
            surface_texture = step4.get("surface_texture", "unknown")
            features["surface_texture"] = surface_texture
    
    # Tracking 전문가에서 경계 정보 추출
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
    matrix: dict = None
) -> dict:
    """
    1차/2차 단락흔 점수 계산
    
    Args:
        visual_features: 추출된 시각적 특징
        matrix: 판정 매트릭스 (기본값: PRIMARY_VS_SECONDARY_MATRIX)
        
    Returns:
        {"primary_score": int, "secondary_score": int, "determination": str}
    """
    if matrix is None:
        matrix = PRIMARY_VS_SECONDARY_MATRIX
    
    primary_score = 0
    secondary_score = 0
    
    # 각 특징별 점수 계산
    for feature_name, feature_value in visual_features.items():
        if feature_value is None:
            continue
        
        feature_matrix = matrix.get(feature_name)
        if not feature_matrix:
            continue
        
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
    
    # 판정
    if primary_score > secondary_score:
        determination = "primary"
    elif secondary_score > primary_score:
        determination = "secondary"
    else:
        determination = "uncertain"
    
    return {
        "primary_score": primary_score,
        "secondary_score": secondary_score,
        "determination": determination,
        "score_difference": abs(primary_score - secondary_score)
    }


def determine_primary_or_secondary(
    visual_features: dict,
    matrix: dict = None
) -> str:
    """
    1차/2차 단락흔 판정
    
    Args:
        visual_features: 추출된 시각적 특징
        matrix: 판정 매트릭스
        
    Returns:
        "primary" | "secondary" | "uncertain"
    """
    score_result = calculate_primary_secondary_score(visual_features, matrix)
    return score_result["determination"]


def resolve_conflict_tracking_vs_dielectric(
    tracking_result: dict,
    dielectric_result: dict,
    tracking_score: float,
    dielectric_score: float
) -> dict:
    """
    Case A: 트래킹 vs 절연열화 상충 해결
    
    Args:
        tracking_result: Tracking 전문가 분석 결과
        dielectric_result: Dielectric 전문가 분석 결과
        tracking_score: Tracking 전문가 신뢰도 점수
        dielectric_score: Dielectric 전문가 신뢰도 점수
        
    Returns:
        {"resolved": bool, "priority": str, "adjusted_scores": dict, "reason": str}
    """
    tracking_step2 = tracking_result.get("step2", {})
    luster_detected = tracking_step2.get("luster_detected", False)
    graphitization = tracking_step2.get("graphitization_evidence", False)
    
    if luster_detected and graphitization:
        # 흑연 광택이 있으면 트래킹 우선
        adjusted_tracking = tracking_score * 1.2
        adjusted_dielectric = dielectric_score * 0.8
        
        return {
            "resolved": True,
            "priority": "tracking",
            "adjusted_scores": {
                "tracking": adjusted_tracking,
                "dielectric": adjusted_dielectric
            },
            "reason": "흑연 광택은 트래킹의 강력한 증거이므로 절연열화보다 우선순위가 높습니다."
        }
    
    return {
        "resolved": False,
        "priority": None,
        "adjusted_scores": {
            "tracking": tracking_score,
            "dielectric": dielectric_score
        },
        "reason": "상충 없음"
    }


def resolve_conflict_mechanical_vs_strand_fracture(
    mechanical_result: dict,
    strand_fracture_result: dict,
    mechanical_score: float,
    strand_fracture_score: float
) -> dict:
    """
    Case B: 압착 vs 반단선 상충 해결
    
    Args:
        mechanical_result: Mechanical 전문가 분석 결과
        strand_fracture_result: StrandFracture 전문가 분석 결과
        mechanical_score: Mechanical 전문가 신뢰도 점수
        strand_fracture_score: StrandFracture 전문가 신뢰도 점수
        
    Returns:
        {"resolved": bool, "priority": str, "adjusted_scores": dict, "reason": str}
    """
    mechanical_step1 = mechanical_result.get("step1", {})
    deformation_detected = mechanical_step1.get("mechanical_deformation_detected", False)
    causal_relationship = mechanical_step1.get("causal_relationship", False)
    
    if deformation_detected and causal_relationship:
        # 압착 흔적이 명확하면 압착 우선
        adjusted_mechanical = mechanical_score * 1.3
        adjusted_strand_fracture = strand_fracture_score * 0.7
        
        return {
            "resolved": True,
            "priority": "mechanical",
            "adjusted_scores": {
                "mechanical": adjusted_mechanical,
                "strand_fracture": adjusted_strand_fracture
            },
            "reason": "압착 흔적이 명확하면 반단선보다 우선하며, 반단선은 압착에 의한 2차적 절단으로 해석됩니다."
        }
    
    return {
        "resolved": False,
        "priority": None,
        "adjusted_scores": {
            "mechanical": mechanical_score,
            "strand_fracture": strand_fracture_score
        },
        "reason": "상충 없음"
    }


def resolve_conflict_shape_vs_surface(
    shape: str,
    surface_texture: str,
    primary_score: float,
    secondary_score: float
) -> dict:
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
    expert_confidence_scores: dict
) -> dict:
    """
    전체 상충 해결 적용
    
    Args:
        expert_analysis_results: 각 전문가의 분석 결과
        expert_confidence_scores: 각 전문가의 신뢰도 점수
        
    Returns:
        {"adjusted_scores": dict, "conflicts": list, "resolutions": list}
    """
    adjusted_scores = expert_confidence_scores.copy()
    conflicts = []
    resolutions = []
    
    # Case A: 트래킹 vs 절연열화
    tracking_result = expert_analysis_results.get("tracking", {})
    dielectric_result = expert_analysis_results.get("dielectric", {})
    tracking_score = expert_confidence_scores.get("tracking", 0)
    dielectric_score = expert_confidence_scores.get("dielectric", 0)
    
    if tracking_result and dielectric_result:
        conflict_a = resolve_conflict_tracking_vs_dielectric(
            tracking_result, dielectric_result, tracking_score, dielectric_score
        )
        if conflict_a["resolved"]:
            conflicts.append("tracking_vs_dielectric")
            resolutions.append(conflict_a)
            adjusted_scores.update(conflict_a["adjusted_scores"])
    
    # Case B: 압착 vs 반단선
    mechanical_result = expert_analysis_results.get("mechanical", {})
    strand_fracture_result = expert_analysis_results.get("strand_fracture", {})
    mechanical_score = expert_confidence_scores.get("mechanical", 0)
    strand_fracture_score = expert_confidence_scores.get("strand_fracture", 0)
    
    if mechanical_result and strand_fracture_result:
        conflict_b = resolve_conflict_mechanical_vs_strand_fracture(
            mechanical_result, strand_fracture_result,
            mechanical_score, strand_fracture_score
        )
        if conflict_b["resolved"]:
            conflicts.append("mechanical_vs_strand_fracture")
            resolutions.append(conflict_b)
            adjusted_scores.update(conflict_b["adjusted_scores"])
    
    return {
        "adjusted_scores": adjusted_scores,
        "conflicts": conflicts,
        "resolutions": resolutions
    }


def apply_evidence_hierarchy(
    expert_scores: dict,
    expert_evidence: dict,
    hierarchy: dict = None
) -> dict:
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
        if not evidence_list:
            weighted_scores[expert_name] = expert_scores.get(expert_name, 0)
            evidence_types[expert_name] = "general_carbonization"
            continue
        
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
        base_score = expert_scores.get(expert_name, 0)
        weight = hierarchy.get(evidence_type, 1.0)
        weighted_scores[expert_name] = base_score * weight
    
    return {
        "weighted_scores": weighted_scores,
        "evidence_types": evidence_types
    }


def calculate_weighted_score(
    expert_scores: dict,
    expert_evidence: dict,
    hierarchy: dict = None
) -> dict:
    """
    가중치 적용 점수 계산 (apply_evidence_hierarchy의 별칭)
    
    Args:
        expert_scores: 각 전문가의 신뢰도 점수
        expert_evidence: 각 전문가의 증거 리스트
        hierarchy: 증거 위계 딕셔너리
        
    Returns:
        apply_evidence_hierarchy()의 반환값과 동일
    """
    return apply_evidence_hierarchy(expert_scores, expert_evidence, hierarchy)

