"""
LangGraph 상태 정의
TypedDict를 사용하여 그래프 상태 스키마를 정의합니다.
"""
import operator
from typing import Annotated, Optional, List, Any
from typing_extensions import TypedDict
import numpy as np


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
    화재조사 멀티 에이전트 상태 스키마
    
    기존 GraphState와 별도로 정의하여 독립적인 그래프로 사용
    """
    payload: List[Any]  # LLM 입력 데이터 (이미지 + 텍스트)
    
    # 전문가 리포트 수집 (Reducer 패턴: 병렬 실행 시 덮어쓰기 방지)
    expert_reports: Annotated[List[str], operator.add]
    
    # 최종 결론
    final_verdict: Optional[str]
    
    # 에러 수집
    errors: Annotated[List[str], operator.add]

