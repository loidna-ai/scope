"""
Component Classifier Models
Pydantic models for structured output from component classification
"""
from pydantic import BaseModel, Field
from typing import Literal


class ComponentClassification(BaseModel):
    """Component classification result with structured output"""
    
    deduced_type: Literal["Wire", "Terminal", "Splice", "Plug", "None"] = Field(
        description="접속부 유형 분류. Wire=전선, Terminal=단자, Splice=접속, Plug=플러그, None=기타"
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
