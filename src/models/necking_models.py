"""
Necking Expert Evidence Models
Pydantic models for structured evidence collection
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from src.models.evidence_models import EvidenceItem

# 공통 Wire 기하학 모델 (Deform과 공유)
from src.models.wire_models import (
    GeometricMeasurement,
    Zone1Reference,
    Zone2Transition,
    Zone3Apex,
    Zone4MeltedMarksBeads,
)

__all__ = [
    "GeometricMeasurement",
    "Zone1Reference",
    "Zone2Transition",
    "Zone3Apex",
    "Zone4MeltedMarksBeads",
    "LogicContrast",
    "FinalVerdict",
    "NeckingEvidenceResult",
]


class ContextAnalysis(BaseModel):
    global_arrangement: str = Field(description="Global arrangement observation", default="관찰 불가")
    fire_pattern: str = Field(description="Fire pattern observation", default="관찰 불가")

class LocationMapping(BaseModel):
    identified_location: str = Field(description="Identified location observation", default="위치 식별 불가")

class CropIdentification(BaseModel):
    crop_description: str = Field(description="Crop area description", default="크롭 영역 식별 불가")





class NeckingEvidenceResult(BaseModel):
    step1_context_analysis: ContextAnalysis = Field(default_factory=ContextAnalysis)
    step2_location_mapping: LocationMapping = Field(default_factory=LocationMapping)
    step3_crop_identification: CropIdentification = Field(default_factory=CropIdentification)
    step4_geometric_measurement: GeometricMeasurement
    step5_extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")
    
    # Legacy compatibility properties
    @property
    def verdict(self) -> str:
        return "판독 보류 (Evidence Collected)"
    
    @property
    def confidence(self) -> int:
        return 0
    
    @property
    def reasoning(self) -> str:
        return "자세한 증거 목록이 생성되었습니다."
