"""
LangGraph 상태 정의
TypedDict를 사용하여 그래프 상태 스키마를 정의합니다.
"""
import operator
from typing import Annotated, Optional, List, Any, Callable
from typing_extensions import TypedDict
import numpy as np


def merge_dicts(left: dict, right: dict) -> dict:
    """
    두 딕셔너리를 병합하는 reducer 함수
    병렬 실행 시 여러 노드에서 동시에 dict를 업데이트할 때 사용
    
    Args:
        left: 기존 딕셔너리
        right: 새로 추가할 딕셔너리
    
    Returns:
        병합된 딕셔너리
    """
    if left is None:
        left = {}
    if right is None:
        right = {}
    result = left.copy()
    result.update(right)
    return result


class GraphState(TypedDict):
    """
    그래프 상태 스키마 (기존 이미지 처리 파이프라인용)
    
    각 노드는 이 상태를 읽고, 업데이트할 필드만 반환합니다 (Partial State).
    """
    # 입력
    input_image_path: str  # 입력 이미지 경로
    
    # 처리 단계별 이미지
    original_image: Optional[np.ndarray]  # 원본 이미지
    cropped_image: Optional[np.ndarray]  # 크롭된 이미지
    enhanced_image: Optional[np.ndarray]  # Real-ESRGAN 향상 이미지
    filtered_image: Optional[np.ndarray]  # CLAHE 필터 적용 이미지
    binary_mask: Optional[np.ndarray]  # 형태학적 분석 마스크
    
    # 분석 결과
    metrics: Optional[dict]  # 형태학적 메트릭스 (circularity, solidity, area)
    analysis_data: Optional[dict]  # LLM 분석용 JSON 데이터
    
    # 에러 수집 (Reducer 패턴 사용)
    errors: Annotated[list[str], operator.add]  # 에러 메시지 수집


class InvestigationState(TypedDict):
    """
    화재조사 멀티 에이전트 상태 스키마 (구조화된 다단계 분석 방식)
    
    기존 GraphState와 별도로 정의하여 독립적인 그래프로 사용
    """
    payload: List[Any]  # LLM 입력 데이터 (이미지 + 텍스트)
    
    # 최종 전문가 리포트
    expert_reports: Annotated[List[str], operator.add]
    
    # 각 전문가의 구조화된 분석 결과 (단계별 결과)
    expert_analysis_results: Annotated[dict, merge_dicts]  # {"contact": {"step1": {...}, "step2": {...}, ...}, ...}
    
    # 각 전문가의 신뢰도 점수
    expert_confidence_scores: Annotated[dict, merge_dicts]  # {"contact": 85, "tracking": 72, ...}
    
    # 각 전문가의 증거
    expert_evidence: Annotated[dict, merge_dicts]  # {"contact": [...], "tracking": [...], ...}
    
    # 최종 결론
    final_verdict: Optional[str]
    
    # 에러 수집
    errors: Annotated[List[str], operator.add]

