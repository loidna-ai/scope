from pydantic import BaseModel, Field
from typing import List, Optional, Any

class EvidenceItem(BaseModel):
    """단일 시각적 증거 항목"""
    hotspot_id: Optional[int] = Field(None, description="증거가 발견된 핫스팟 ID (전체 이미지인 경우 None)")
    visual_fact: str = Field(description="관찰된 객관적인 시각적 특징 (결론을 배제하고 사실만 기술)")
    certainty: float = Field(description="해당 시각적 특징이 존재한다는 것에 대한 확신도 (0~100)")
    
class ExpertReport(BaseModel):
    """전문가가 아비터에게 전달하는 최종 리포트 구조체 (증명 중심)"""
    expert_id: str = Field(description="전문가 식별자 (예: Contact_Expert)")
    evidence_list: List[EvidenceItem] = Field(default_factory=list, description="취합된 시각적 증거 리스트")
    preliminary_opinion: str = Field(description="해당 도메인 관점에서의 종합적인 예비 소견")
    confidence: float = Field(description="결론에 대한 도메인 차원의 최종 확신 정도 (0~100)")

    def to_markdown(self) -> str:
        """아비터 등 LLM이 쉽게 식별할 수 있도록 마크다운 형식으로 렌더링"""
        lines = [f"### Expert Report: {self.expert_id}"]
        lines.append(f"**Domain Confidence:** {self.confidence}%")
        lines.append("\n**[Visual Evidence List]**")
        if not self.evidence_list:
            lines.append("- (No evidence found)")
        for ev in self.evidence_list:
            ref = f"(Hotspot #{ev.hotspot_id})" if ev.hotspot_id is not None else "(Global)"
            lines.append(f"- {ref} {ev.visual_fact} (Certainty: {ev.certainty}%)")
        lines.append("\n**[Preliminary Opinion]**")
        lines.append(f"{self.preliminary_opinion}\n")
        return "\n".join(lines)
