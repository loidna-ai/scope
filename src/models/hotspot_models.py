"""
Hotspot Detector Models
Pydantic models for structured output from hotspot detection
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class BoundingBox2D(BaseModel):
    """2D Bounding Box (정규화 좌표 0-1000)"""
    ymin: int = Field(ge=0, le=1000, description="Y 최소값 (정규화)")
    xmin: int = Field(ge=0, le=1000, description="X 최소값 (정규화)")
    ymax: int = Field(ge=0, le=1000, description="Y 최대값 (정규화)")
    xmax: int = Field(ge=0, le=1000, description="X 최대값 (정규화)")


class Hotspot(BaseModel):
    """개별 Hotspot 정보"""
    id: int = Field(ge=1, description="Hotspot 고유 ID")
    
    damage_type: str = Field(
        description="손상 유형 (예: wire_necking, bead_formation, tracking, thermal_damage 등)"
    )
    
    box_2d: BoundingBox2D = Field(
        description="2D Bounding Box (정규화 좌표 0-1000)"
    )
    
    severity_score: int = Field(
        ge=0, 
        le=100,
        description="심각도 점수 (0-100)"
    )
    
    location_description: str = Field(
        description="위치 설명 (예: 좌측 상단, 중앙 하단 등)"
    )
    
    visual_evidence: str = Field(
        description="시각적 증거 요약 (2-3문장)"
    )


class HotspotDetectionResult(BaseModel):
    """Hotspot Detection 전체 결과"""
    hotspots: List[Hotspot] = Field(
        default_factory=list,
        description="탐지된 Hotspot 리스트"
    )
    
    total_count: int = Field(
        ge=0,
        description="탐지된 총 Hotspot 개수"
    )
    
    analysis_summary: str = Field(
        description="전체 분석 요약 (3-5문장)"
    )
