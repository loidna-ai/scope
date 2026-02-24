"""
공통 상태 정의 모듈
Contact, Necking, Deform 전문가 노드에서 공유하는 공통 TypedDict
"""
from typing import Dict, Any, List, Optional, Annotated
import operator
from typing_extensions import TypedDict


class WorkerState(TypedDict):
    """
    Map-Reduce 패턴의 Worker 노드 입력 상태.
    LangGraph Send API를 통해 각 Hotspot을 개별 Worker에 전달할 때 사용.
    """
    current_hotspot: Dict[str, Any]
    image_path: str


class BaseExpertState(TypedDict):
    """
    전문가 그래프 상태 (Map-Reduce Pattern) 공통 베이스.
    Contact, Necking, Deform 등 각 전문가 노드들이 공통으로 사용하는 상태 필드.
    """
    # 기본 메시지 상태 (LangGraph 요구사항)
    messages: List[Any]
    
    # 이미지 경로
    image_path: str
    
    # 1. 탐지 단계 상태
    hotspots: List[Dict[str, Any]]  # 탐지된 모든 핫스팟
    preprocessed_hotspots: Optional[List[Dict[str, Any]]]  # [#5 Preprocessor] 전처리 완료 핫스팟
    
    # 2. Worker 결과 집계 (Map-Reduce)
    preliminary_assessments: Annotated[List[Dict[str, Any]], operator.add]  # Worker가 수집한 증거 누적
    analysis_results: Annotated[List[Dict[str, Any]], operator.add]  # Notebook 시각화용 결과 누적

    # 3. Supervisor 판정 결과
    final_verdict: Optional[Dict[str, Any]]  # {"conclusion": str, "confidence": float, "reasoning": str}
    debate_context: Optional[Dict[str, Any]]  # Debate 필요 시 컨텍스트 전달
    
    # 4. Debate 시스템 (Analyst-Critic)
    debate_iteration: int  # Debate 반복 횟수 (무한 루프 방지)
    debate_messages: Annotated[List[str], operator.add]  # Analyst-Critic 대화 이력
    
    # [Phase 2] Pydantic 구조화 (타입 안전 - Debate 노드용)
    analyst_hypothesis: Optional[Any]  # AnalystHypothesis Pydantic 객체
    critique_result: Optional[Any]  # CritiqueResult Pydantic 객체
    
    # [Legacy] 하위 호환성을 위한 필드 (문자열 형식)
    current_hypothesis: Optional[str]  # Analyst 가설 (문자열 형식)
    critique_points: Optional[str]  # Critic 비평 (문자열 형식)
    
    verdict_report: Optional[str]
    verdict_confidence: Optional[float]
    verdict_result: Optional[Dict[str, Any]]
