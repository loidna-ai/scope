"""
Aging Expert Evidence Models
Pydantic models for structured evidence collection (Wire, PCB)
Contact/Deform/Necking과 동일한 패턴
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from src.models.evidence_models import EvidenceItem

__all__ = [
    "AgingWireEvidenceResult",
    "AgingPCBEvidenceResult",
]


# ===== Aging Wire Models =====

class AgingContextAnalysis(BaseModel):
    global_arrangement: str = Field(default="관찰 불가", description="전선 배치 및 설치 환경")
    environmental_stress: str = Field(default="관찰 불가", description="물리적/열적 스트레스 여건")


class AgingLocationMapping(BaseModel):
    identified_location: str = Field(default="위치 식별 불가", description="Image_B가 Image_A의 어느 지점인지")


class AgingCropIdentification(BaseModel):
    crop_description: str = Field(default="크롭 영역 식별 불가", description="확대 부위 이미지 설명")
    observable_degradation: bool = Field(default=False, description="관찰 가능한 열화 여부")


class Zone1ColorTexture(BaseModel):
    color_degradation: str = Field(default="관찰 불가", description="변색 관찰 결과")
    texture_loss: str = Field(default="관찰 불가", description="질감 및 광택 저하 상태")


class Zone2Mechanical(BaseModel):
    hardening_brittleness: str = Field(default="관찰 불가", description="경화 및 취성 징후")
    micro_crazing: str = Field(default="관찰 불가", description="미세 균열 관찰 결과")


class Zone3ThermalShrinkage(BaseModel):
    shrinkage_exposure: str = Field(default="관찰 불가", description="수축에 의한 도체 노출 여부")
    peeling_crack: str = Field(default="관찰 불가", description="박리 및 떨어져 나감 현상")


class Zone4Exclusion(BaseModel):
    direct_burn_signs: str = Field(default="관찰 불가", description="단순 연소/용융 징후 유무")
    mechanical_cut: str = Field(default="관찰 불가", description="기계적 절단/손상 유무")


class AgingInsulationInspection(BaseModel):
    zone1_color_texture: Zone1ColorTexture = Field(default_factory=Zone1ColorTexture)
    zone2_mechanical: Zone2Mechanical = Field(default_factory=Zone2Mechanical)
    zone3_thermal_shrinkage: Zone3ThermalShrinkage = Field(default_factory=Zone3ThermalShrinkage)
    zone4_exclusion: Zone4Exclusion = Field(default_factory=Zone4Exclusion)


class AgingWireEvidenceResult(BaseModel):
    """Aging Wire(전선) 전문가 증거 수집 결과"""
    step1_context_analysis: AgingContextAnalysis = Field(default_factory=AgingContextAnalysis)
    step2_location_mapping: AgingLocationMapping = Field(default_factory=AgingLocationMapping)
    step3_crop_identification: AgingCropIdentification = Field(default_factory=AgingCropIdentification)
    step4_insulation_inspection: AgingInsulationInspection = Field(default_factory=AgingInsulationInspection)
    step5_extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")

    # Legacy compatibility properties
    @property
    def visual_observation(self) -> str:
        """하위 호환성을 위한 visual_observation 추출"""
        zone1 = self.step4_insulation_inspection.zone1_color_texture
        zone2 = self.step4_insulation_inspection.zone2_mechanical
        zone3 = self.step4_insulation_inspection.zone3_thermal_shrinkage
        
        desc_parts = [
            f"Zone 1 (색상/질감): {zone1.color_degradation[:100]}...",
            f"Zone 2 (기계적 물성): {zone2.hardening_brittleness[:100]}...",
            f"Zone 3 (열수축/박리): {zone3.shrinkage_exposure[:100]}..."
        ]
        return " | ".join(desc_parts)

    @property
    def verdict(self) -> str:
        return "판독 보류 (Evidence Collected)"

    @property
    def confidence(self) -> int:
        return 0

    @property
    def reasoning(self) -> str:
        return "자세한 증거 목록이 생성되었습니다."


# ===== Aging PCB Models =====

class AgingPCBEvidenceResult(BaseModel):
    """Aging PCB(기판) 전문가 증거 수집 결과"""
    visual_observation: str = Field(default="", description="기판의 전반적인 색상 변화, 코팅 상태 등")
    extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")

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
