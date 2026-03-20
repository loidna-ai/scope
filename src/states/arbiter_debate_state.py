"""
Arbiter Debate State 정의
논쟁 시스템을 위한 독립적인 State 스키마
"""
from __future__ import annotations  # 모든 타입 힌트를 문자열로 평가하여 런타임 평가 방지

from typing import Literal, TypedDict, List, Dict, Any, Optional
from typing_extensions import Annotated
import operator

# FinalVerdictResult를 런타임에 사용 가능하도록 import
# verdict_models는 arbiter_debate_state를 import하지 않으므로 순환 참조 없음
try:
    from src.models.verdict_models import FinalVerdictResult
except ImportError:
    # Import 실패 시 Any로 대체 (타입 체크용)
    FinalVerdictResult = Any

# 논쟁 단계 타입
DebateStage = Literal["opening", "rebuttal", "final_argument", "judgment"]

# 전문가 이름 타입
ExpertName = Literal["contact", "deform", "necking", "aging"]

class DebateMessage(TypedDict):
    """논쟁 메시지 구조"""
    speaker: str  # "contact", "deform", "necking", "aging", "fact_checker", "moderator", "judge"
    content: str  # 메시지 내용
    validated: bool  # Fact Checker 검증 여부
    stage: DebateStage  # 논쟁 단계
    round_num: int  # 라운드 번호

class ExpertOpinion(TypedDict):
    """전문가 의견 구조"""
    conclusion: str  # 결론 (예: "접촉불량", "압착")
    confidence: int  # 신뢰도 점수 (0-100)
    verdict: str  # 상세 판정
    visual_description: str  # 시각적 특징 설명
    evidence: List[str]  # 증거 리스트
    reasoning: str  # 논리적 근거

class ArbiterDebateState(TypedDict):
    """
    Arbiter Debate 서브그래프 상태 스키마
    
    기존 전문가 서브그래프와 동일한 패턴으로 독립적인 State 사용
    """
    # 입력 데이터 (래퍼 노드에서 InvestigationState에서 추출하여 설정)
    expert_opinions: Dict[ExpertName, ExpertOpinion]  # 각 전문가의 구조화된 의견
    expert_reports: List[str]  # 전문가 리포트 텍스트 리스트
    expert_confidence_scores: Dict[str, int]  # 전문가별 신뢰도 점수
    expert_evidence: Dict[str, List[Dict]]  # 전문가별 증거 리스트
    spatial_summary: str  # 넓은 범위(Wide Mode) 공간적 분포 요약
    
    # 논쟁 진행 상태
    debate_messages: Annotated[List[DebateMessage], operator.add]  # 논쟁 메시지 히스토리
    current_stage: DebateStage  # 현재 논쟁 단계
    current_round: int  # 현재 라운드 번호
    current_speaker: Optional[ExpertName]  # 현재 발언자
    
    # Fact Check 상태
    fact_check_failures: Dict[ExpertName, int]  # 각 전문가의 Fact Check 실패 횟수
    
    # 최종 결과
    final_verdict: Optional[str]  # 최종 판정 리포트 (하위 호환성)
    final_verdict_structured: Optional["FinalVerdictResult"]  # 구조화된 최종 판정 데이터
    consensus_reached: bool  # 합의 도달 여부
    
    # 에러 수집
    errors: Annotated[List[str], operator.add]  # 에러 메시지 리스트
