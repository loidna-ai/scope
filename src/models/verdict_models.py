"""
최종 판정 구조화 모델
Judge/Arbiter 노드에서 구조화된 출력으로 사용
전문가 노드의 AnalystHypothesis와 동일한 패턴
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Literal


class ZoneInfo(BaseModel):
    """Zone별 상세 정보"""
    zone_number: int = Field(
        ge=1, 
        le=10, 
        description="Zone 번호 (예: 1, 3, 4)"
    )
    description: str = Field(
        description="Zone 설명 (예: 압착부 경계, 도체 표면, 말단부)"
    )
    observation: str = Field(
        description="Zone 관찰 결과 (구체적인 증거 및 특징)"
    )


class ExpertReportSummary(BaseModel):
    """전문가 리포트 요약 (최종 판정에 포함)"""
    expert_name: Literal["CONTACT", "DEFORM", "NECKING", "AGING", "N/A"] = Field(
        description="전문가 이름 (비활성 시 N/A)"
    )
    conclusion: Literal["유력", "의심", "아님", "해당 없음", "판독 불가"] = Field(
        description="판정 결과"
    )
    confidence: Optional[float] = Field(
        None, 
        ge=0, 
        le=100, 
        description="신뢰도 퍼센트 (해당 없음일 경우 None)"
    )
    key_evidence: str = Field(
        description="핵심 근거 한 줄 요약"
    )


class FinalVerdictResult(BaseModel):
    """최종 판정 구조화 데이터
    
    Judge 노드에서 생성되는 구조화된 최종 판정 결과
    전문가 노드의 AnalystHypothesis와 동일한 패턴으로 설계됨
    """
    # 핵심 정보
    verdict: str = Field(
        description="최종 판정 결과 (예: 접촉불량(유력), 압착·손상(의심))"
    )
    confidence_score: float = Field(
        ge=0, 
        le=100, 
        description="신뢰도 점수 (0-100)"
    )
    confidence_level: Literal["High", "Medium", "Low"] = Field(
        description="신뢰도 레벨"
    )
    
    # 판정 근거
    reasoning_summary: str = Field(
        description="판정의 논리적 근거 요약 (2-3문장)"
    )
    key_evidence: List[str] = Field(
        max_length=5,
        default_factory=list,
        description="판정에 사용된 핵심 증거 목록 (최대 5개)"
    )
    
    # Zone 정보
    zones: List[ZoneInfo] = Field(
        default_factory=list,
        description="Zone별 상세 정보 (Zone 1, 3, 4 등)"
    )
    
    # 전문가 요약 (활성 전문가만 포함, 2~4명)
    expert_summaries: List[ExpertReportSummary] = Field(
        min_length=2,
        max_length=4,
        description="각 전문가의 판정 요약 (활성 전문가만: Contact, Necking 등)"
    )
    
    # 권고 사항
    recommendations: List[str] = Field(
        default_factory=list,
        description="추가 조사 권고 사항"
    )
    
    # 사용자용 리포트 본문 (선택적)
    report_body_markdown: Optional[str] = Field(
        None,
        description="사용자에게 보여줄 상세 리포트 본문 (Markdown 형식). "
                    "없으면 구조화된 데이터로부터 자동 생성 가능."
    )
    
    @field_validator('confidence_score')
    @classmethod
    def validate_confidence_score(cls, v):
        """신뢰도 점수 검증"""
        if not 0 <= v <= 100:
            raise ValueError("confidence_score must be between 0 and 100")
        return v
    
    @model_validator(mode='after')
    def validate_expert_summaries(self):
        """전문가 요약 검증 (활성 전문가만, 2~4명, 중복 없음)"""
        # N/A 제외한 실제 전문가 이름 중복 확인
        expert_names = [s.expert_name for s in self.expert_summaries if s.expert_name != "N/A"]
        if len(expert_names) != len(set(expert_names)):
            raise ValueError("expert_summaries must have unique expert names (excluding N/A)")
        return self
    
    def get_confidence_level(self) -> str:
        """신뢰도 점수로부터 레벨 자동 계산 (검증용)"""
        if self.confidence_score >= 80:
            return "High"
        elif self.confidence_score >= 60:
            return "Medium"
        else:
            return "Low"
    
    def to_text_summary(self) -> str:
        """텍스트 요약 생성 (하위 호환성용)"""
        lines = [
            f"**최종 판정**: {self.verdict}",
            f"**신뢰도**: {self.confidence_score:.1f}% ({self.confidence_level})",
            "",
            "**판정 근거:**",
            self.reasoning_summary,
            "",
            "**핵심 증거:**",
        ]
        
        for i, evidence in enumerate(self.key_evidence, 1):
            lines.append(f"{i}. {evidence}")
        
        if self.zones:
            lines.append("")
            lines.append("**Zone 정보:**")
            for zone in self.zones:
                lines.append(f"- Zone {zone.zone_number} ({zone.description}): {zone.observation}")
        
        if self.recommendations:
            lines.append("")
            lines.append("**추가 조사 권고 사항:**")
            for i, rec in enumerate(self.recommendations, 1):
                lines.append(f"{i}. {rec}")
        
        return "\n".join(lines)

class ContactSupervisorVerdict(BaseModel):
    final_conclusion: Literal[
        "접촉불량", "접촉불량 의심", "접촉불량 아님", "판독 불가"
    ] = Field(description="접촉불량 | 접촉불량 의심 | 접촉불량 아님 | 판독 불가")
    final_confidence: int = Field(
        ge=0, le=100, description="Final confidence score (0-100)"
    )
    key_evidence_summary: str = Field(
        description="Summary of key facts driving the decision"
    )
    reasoning_process: str = Field(
        description="Synthesis of worker reports and conflict resolution"
    )

class DeformSupervisorVerdict(BaseModel):
    final_conclusion: Literal[
        "압착·손상", "압착·손상 의심", "압착·손상 아님", "판독 불가"
    ] = Field(description="압착·손상 | 압착·손상 의심 | 압착·손상 아님 | 판독 불가")
    final_confidence: int = Field(
        ge=0, le=100, description="Final confidence score (0-100)"
    )
    key_evidence_summary: str = Field(
        description="Summary of key facts driving the decision"
    )
    reasoning_process: str = Field(
        description="Synthesis of worker reports and conflict resolution"
    )

class NeckingSupervisorVerdict(BaseModel):
    final_conclusion: Literal[
        "반단선", "반단선 의심", "반단선 아님", "판독 불가"
    ] = Field(description="반단선 | 반단선 의심 | 반단선 아님 | 판독 불가")
    final_confidence: int = Field(
        ge=0, le=100, description="Final confidence score (0-100)"
    )
    key_evidence_summary: str = Field(
        description="Summary of key facts driving the decision"
    )
    reasoning_process: str = Field(
        description="Synthesis of worker reports and conflict resolution"
    )

class AgingSupervisorVerdict(BaseModel):
    final_conclusion: Literal[
        "경년열화 심각", "경년열화 의심", "경년열화 아님", "판독 불가"
    ] = Field(description="경년열화 심각 | 경년열화 의심 | 경년열화 아님 | 판독 불가")
    final_confidence: int = Field(
        ge=0, le=100, description="Final confidence score (0-100)"
    )
    key_evidence_summary: str = Field(
        description="Summary of key facts driving the decision"
    )
    reasoning_process: str = Field(
        description="Synthesis of worker reports and conflict resolution"
    )

class TrackingSupervisorVerdict(BaseModel):
    final_conclusion: Literal[
        "트래킹", "트래킹 의심", "트래킹 아님", "판독 불가"
    ] = Field(description="트래킹 | 트래킹 의심 | 트래킹 아님 | 판독 불가")
    final_confidence: int = Field(
        ge=0, le=100, description="Final confidence score (0-100)"
    )
    key_evidence_summary: str = Field(
        description="Summary of key facts driving the decision"
    )
    reasoning_process: str = Field(
        description="Synthesis of worker reports and conflict resolution"
    )
