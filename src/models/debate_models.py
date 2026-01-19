"""
Analyst-Critic Debate를 위한 Pydantic 모델
구조화된 통신 및 타입 안전성 보장
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal


class HypothesisData(BaseModel):
    """
    구조화된 가설 데이터 (Core Hypothesis Data)
    """
    conclusion: str = Field(
        ..., 
        description="판정 결과: 반단선 (Confirmed) / 반단선 의심 (Suspected) / 반단선 아님 (Not Necking) / 판독 불가 (Indeterminate)"
    )
    probability: int = Field(
        ..., 
        description="확률 (0-100)"
    )
    key_evidence: List[str] = Field(
        default_factory=list,
        description="핵심 증거 리스트"
    )
    reasoning: str = Field(
        ..., 
        description="판정 근거"
    )

    def to_string(self) -> str:
        return f"{self.conclusion} ({self.probability}%)"


class AnalystHypothesis(BaseModel):
    """
    Analyst(분석관)의 가설 출력 구조 (Initial & Reanalysis 통합)
    """
    
    # [Scenario A] 초기 분석 (Initial Analysis) - Flat Structure
    conclusion: Optional[str] = Field(None, description="초기 판정 결과")
    probability: Optional[int] = Field(None, description="초기 확률")
    key_evidence: Optional[List[str]] = Field(None, description="초기 핵심 증거")
    reasoning: Optional[str] = Field(None, description="초기 판정 근거")
    
    # [Scenario B] 재분석 (Reanalysis) - Nested Structure
    critique_is_valid: Optional[bool] = Field(None, description="비평 타당성")
    rebuttal_or_acceptance: Optional[str] = Field(None, description="비평 수용/반박 내용")
    revised_hypothesis: Optional[HypothesisData] = Field(None, description="수정된 가설 데이터")
    
    def get_hypothesis_data(self) -> HypothesisData:
        """현재 유효한 가설 데이터 반환 (revised 우선)"""
        if self.revised_hypothesis:
            return self.revised_hypothesis
        
        # Initial 데이터가 있으면 반환
        if self.conclusion and self.probability is not None:
            return HypothesisData(
                conclusion=self.conclusion,
                probability=self.probability,
                key_evidence=self.key_evidence or [],
                reasoning=self.reasoning or ""
            )
            
        # Fallback (데이터 없음)
        return HypothesisData(
            conclusion="판독 불가 (Data Error)",
            probability=0,
            key_evidence=[],
            reasoning="데이터 파싱 실패 또는 누락"
        )

    def get_hypothesis(self) -> str:
        """문자열 형태 가설 반환 (Legacy 호환용)"""
        data = self.get_hypothesis_data()
        return data.to_string()


class CritiqueResult(BaseModel):
    """
    Critic(비평가)의 검증 결과 구조
    
    is_approved: 최종 승인 여부 (True면 합의, False면 재분석 필요)
    objection_type: 이의 유형 ("NO_OBJECTION" or 구체적 문제 유형)
    flaws: 발견된 논리적/시각적 오류 리스트 (구체적으로)
    hotspots_mentioned: 지적한 Hotspot ID 리스트 (Analyst가 재분석 시 활용)
    critical_question: 핵심 질문
    alternative_interpretation: 대안 해석
    suggestion_for_analyst: Analyst가 다음 턴에 해야 할 행동
    """
    
    # 최종 승인 여부 (핵심!)
    is_approved: bool = Field(
        description="가설 승인 여부 (True: 합의/종료, False: 재분석 필요)"
    )
    
    # 이의 유형
    objection_type: Literal[
        "NO_OBJECTION",
        "증거 과대해석",
        "프로파일 누락 간과",
        "대안 가설 미검토",
        "Hotspot 간 불일치"
    ] = Field(
        description="이의 유형 (NO_OBJECTION이면 is_approved=True여야 함)"
    )
    
    # 구조화된 오류 리스트
    flaws: List[str] = Field(
        default_factory=list,
        description="발견된 오류 리스트 (각 항목은 구체적으로, 예: 'Hotspot #3: 슬리빙 불명확')"
    )
    
    # 언급된 Hotspot ID (자동 추출 불필요!)
    hotspots_mentioned: List[int] = Field(
        default_factory=list,
        description="지적한 Hotspot ID 리스트 (Analyst 재분석 시 집중 대상)"
    )
    
    # 핵심 질문
    critical_question: Optional[str] = Field(
        default=None,
        description="분석관에게 던지는 핵심 질문"
    )
    
    # 대안 해석
    alternative_interpretation: Optional[str] = Field(
        default=None,
        description="대안적 해석 제시"
    )
    
    # 다음 행동 지침
    suggestion_for_analyst: Optional[str] = Field(
        default=None,
        description="분석관이 다음 턴에 확인해야 할 구체적인 사항 (예: 'Hotspot #2 ROI에서 Pixel(450, 230) 재확인')"
    )
    
    def has_objections(self) -> bool:
        """이의가 있는지 확인"""
        return not self.is_approved or self.objection_type != "NO_OBJECTION"


# 유틸리티 함수
def create_no_objection() -> CritiqueResult:
    """NO_OBJECTION 결과 생성 헬퍼"""
    return CritiqueResult(
        is_approved=True,
        objection_type="NO_OBJECTION",
        flaws=[],
        hotspots_mentioned=[],
        critical_question=None,
        alternative_interpretation=None,
        suggestion_for_analyst=None
    )
