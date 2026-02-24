"""
Necking Expert Evidence Models
Pydantic models for structured evidence collection
"""
from pydantic import BaseModel, Field
from typing import Literal

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


class LogicContrast(BaseModel):
    logic_refuting: str = Field(description="Evidence refuting necking")
    logic_supporting: str = Field(description="Evidence supporting necking")


class FinalVerdict(BaseModel):
    conclusion: Literal[
        "반단선", "반단선 의심", "반단선 아님", "판독 불가"
    ] = Field(description="반단선 | 반단선 의심 | 반단선 아님 | 판독 불가")
    confidence_score: int = Field(ge=0, le=100)
    final_reasoning: str = Field(description="Summary of reasoning")


class NeckingEvidenceResult(BaseModel):
    step1_context_analysis: ContextAnalysis = Field(default_factory=ContextAnalysis)
    step2_location_mapping: LocationMapping = Field(default_factory=LocationMapping)
    step3_crop_identification: CropIdentification = Field(default_factory=CropIdentification)
    step4_geometric_measurement: GeometricMeasurement
    step5_logic_contrast: LogicContrast
    step6_verdict: FinalVerdict
