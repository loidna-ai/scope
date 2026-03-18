"""
Component Classifier Models
전기 부품 유형 식별(Component Classification) 구조화 출력용 Pydantic 모델

- ComponentClassification: Contact/Deform/Necking 전문가 노드에서 사용
"""
from typing import Literal

from pydantic import BaseModel, Field


class ComponentClassification(BaseModel):
    """전기 부품 유형 식별 결과."""

    deduced_type: Literal["Wire", "Terminal", "Splice", "Plug", "None"] = Field(
        description="접속부 유형: Wire=전선(상/하단 파단면 포함), Terminal=단자, Splice=접속(2개 이상 타 전선의 의도적 결합), Plug=플러그, None=기타"
    )
    visual_description: str = Field(
        description="관찰된 시각적 특징 요약 (2-3문장)"
    )
    confidence: int = Field(
        ge=0,
        le=100,
        description="분류 신뢰도 (0-100)"
    )
    reasoning: str = Field(
        description="분류 근거 (왜 이렇게 판단했는지)"
    )
