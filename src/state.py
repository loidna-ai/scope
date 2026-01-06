"""
LangGraph 상태 정의
TypedDict를 사용하여 그래프 상태 스키마를 정의합니다.
"""
import operator
from typing import Annotated, Optional, List, Any, Callable, Dict
from typing_extensions import TypedDict
import numpy as np
from langgraph.graph import MessagesState

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

def keep_first(left: List[Any], right: List[Any]) -> List[Any]:
    """
    첫 번째 값을 유지하는 reducer 함수
    payload는 읽기 전용이므로 항상 첫 번째 값을 유지
    
    Args:
        left: 기존 값
        right: 새 값
    
    Returns:
        첫 번째 값 (left가 비어있지 않으면 left, 아니면 right)
    """
    # left가 None이 아니고 비어있지 않으면 left 반환
    if left is not None and len(left) > 0:
        return left
    # left가 None이거나 비어있으면 right 반환
    return right if right is not None else []

def keep_last(left: Optional[str], right: Optional[str]) -> Optional[str]:
    """
    마지막 값을 유지하는 reducer 함수
    final_verdict는 마지막에 설정된 값만 유지 (None이 아닌 값 우선)
    
    Args:
        left: 기존 값
        right: 새 값
    
    Returns:
        마지막 값 (None이 아닌 값 우선)
    """
    # None이 아닌 값이 있으면 그것을 반환, 둘 다 None이면 None 반환
    if right is not None:
        return right
    return left

def keep_last_dict(left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    마지막 값을 유지하는 reducer 함수 (Dict 타입용)
    context는 마지막에 설정된 값만 유지 (None이 아닌 값 우선)
    
    Args:
        left: 기존 값
        right: 새 값
    
    Returns:
        마지막 값 (None이 아닌 값 우선)
    """
    # None이 아닌 값이 있으면 그것을 반환, 둘 다 None이면 None 반환
    if right is not None:
        return right
    return left

def keep_last_bytes(left: Optional[bytes], right: Optional[bytes]) -> Optional[bytes]:
    """
    마지막 값을 유지하는 reducer 함수 (bytes 타입용)
    각 서브그래프의 캐시는 마지막에 설정된 값만 유지 (None이 아닌 값 우선)
    
    Args:
        left: 기존 값
        right: 새 값
    
    Returns:
        마지막 값 (None이 아닌 값 우선)
    """
    # None이 아닌 값이 있으면 그것을 반환, 둘 다 None이면 None 반환
    if right is not None:
        return right
    return left

def keep_last_list(left: Optional[List[Any]], right: Optional[List[Any]]) -> Optional[List[Any]]:
    """
    마지막 값을 유지하는 reducer 함수 (List 타입용)
    react_agent_messages는 마지막에 설정된 값만 유지 (None이 아닌 값 우선)
    
    Args:
        left: 기존 값
        right: 새 값
    
    Returns:
        마지막 값 (None이 아닌 값 우선)
    """
    
    # None이 아닌 값이 있으면 그것을 반환, 둘 다 None이면 None 반환
    if right is not None:
        return right
    return left

class InvestigationState(TypedDict):
    """
    화재조사 멀티 에이전트 상태 스키마 (구조화된 다단계 분석 방식)
    
    기존 GraphState와 별도로 정의하여 독립적인 그래프로 사용
    """
    payload: Annotated[List[Any], keep_first]  # LLM 입력 데이터 (이미지 + 텍스트) - 읽기 전용
    
    # 최종 전문가 리포트
    expert_reports: Annotated[List[str], operator.add]
    
    # 각 전문가의 구조화된 분석 결과 (단계별 결과)
    expert_analysis_results: Annotated[dict, merge_dicts]  # {"contact": {"step1": {...}, "step2": {...}, ...}, ...}
    
    # 각 전문가의 신뢰도 점수
    expert_confidence_scores: Annotated[dict, merge_dicts]  # {"contact": 85, "tracking": 72, ...}
    
    # 각 전문가의 증거
    expert_evidence: Annotated[dict, merge_dicts]  # {"contact": [...], "tracking": [...], ...}
    
    # 최종 결론
    final_verdict: Annotated[Optional[str], keep_last]  # 마지막에 설정된 값만 유지
    
    # 에러 수집
    errors: Annotated[List[str], operator.add]
    
    # ReAct 에이전트 메시지 히스토리 (도구 사용 과정 추적)
    react_agent_messages: Annotated[Optional[List[Dict[str, Any]]], keep_last_list]  # ReAct 에이전트의 전체 메시지 히스토리 (마지막 값만 유지)
    
    # ReAct 에이전트를 위한 컨텍스트 정보
    context: Annotated[Optional[Dict[str, Any]], keep_last_dict]  # 이미지 경로 등 컨텍스트 정보 (마지막 값만 유지)
    
    # ReAct 에이전트를 위한 작업 설명 (이미지 경로 포함)
    task: Annotated[Optional[str], keep_last]  # 수행할 작업 설명 (이미지 경로 포함 가능)

class ReActState(MessagesState):
    """
    ReAct 에이전트 상태 (MessagesState 확장)
    
    LangGraph 공식 권장 방식:
    - MessagesState를 상속받아 messages 필드 자동 포함
    - reducer 기능 자동 적용 (operator.add)
    - 추가 필드는 선택적으로 정의
    
    참고: TypedDict는 런타임 기본값을 제공하지 않으므로,
    초기 상태 설정 시 명시적으로 값을 제공해야 합니다.
    """
    # 추가 컨텍스트 (선택적)
    task: Optional[str]  # 수행할 작업 설명
    context: Optional[Dict[str, Any]]  # 컨텍스트 정보
