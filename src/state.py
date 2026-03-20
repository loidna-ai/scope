"""
LangGraph 상태 정의
TypedDict를 사용하여 그래프 상태 스키마를 정의합니다.
"""
import operator
from typing import Annotated, Optional, List, Any, Callable, Dict
from typing_extensions import TypedDict
import numpy as np
from langgraph.graph import MessagesState
from src.models.hotspot_models import UnifiedHotspot

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
    react_agent_messages, arbiter_debate_messages는 마지막에 설정된 값만 유지 (None이 아닌 값 우선)
    
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
    
    # [Memory Optimization] 이미지 경로 (바이너리 대신 경로 전달)
    image_path: Annotated[Optional[str], keep_last]
    image_paths: Annotated[Optional[List[str]], keep_last_list]  # 다중 이미지 통합 분석용
    
    # 공통 Hotspot 탐지 결과 (메인 그래프에서 생성)
    hotspots: Annotated[Optional[List[UnifiedHotspot]], keep_last]  # 마지막에 설정된 값만 유지

    # [#5 Preprocessor] 전처리 완료 Hotspot 목록
    # preprocessor_node가 Crop+Classification+Enhancement를 1회 수행한 결과.
    # 각 항목에는 원본 hotspot 필드 외에 roi_image_path, component_type, _preprocessed=True가 추가됨.
    # 전문가 Worker는 _preprocessed=True이면 Crop/Classification/Enhancement 단계를 건너뜀.
    preprocessed_hotspots: Annotated[Optional[List[UnifiedHotspot]], keep_last]

    # total_count 보정 값 (hotspot_detector_node에서 설정)
    corrected_total_count: Annotated[Optional[int], keep_last]
    
    # 분석 상태 플래그 (hotspot_detector_node에서 설정)
    # 값: "NO_HOTSPOTS_DETECTED" 등
    analysis_status: Annotated[Optional[str], keep_last]
    
    # 최종 전문가 리포트
    expert_reports: Annotated[List[str], operator.add]
    
    # 각 전문가의 구조화된 분석 결과 (단계별 결과)
    expert_analysis_results: Annotated[dict, merge_dicts]  # {"contact": {"step1": {...}, "step2": {...}, ...}, ...}
    
    # 각 전문가의 신뢰도 점수
    expert_confidence_scores: Annotated[dict, merge_dicts]  # {"contact": 85, "tracking": 72, ...}
    
    # 각 전문가의 증거 (Evidence-First Architecture: ExpertReport 객체 혹은 증거 목록 리스트)
    expert_evidence: Annotated[dict, merge_dicts]  # {"contact": ExpertReport(...), "tracking": ...}
    
    # 최종 결론
    final_verdict: Annotated[Optional[str], keep_last]  # 마지막에 설정된 값만 유지
    final_verdict_structured: Annotated[Optional[Any], keep_last]  # 구조화된 최종 판정 데이터 (FinalVerdictResult)
    
    # 아비터 토론 메시지
    arbiter_debate_messages: Annotated[Optional[List[Dict[str, Any]]], keep_last_list]  # 아비터 토론 메시지 히스토리
    
    # 에러 수집
    errors: Annotated[List[str], operator.add]
    
    # 시각화 이미지 경로
    visual_report_path: Annotated[Optional[str], keep_last]

    # 결과 저장 디렉토리 (visualization_node에서 시각화 이미지 저장 위치로 사용)
    output_dir: Annotated[Optional[str], keep_last]
    

