"""
Tracking Expert Evidence Models
Pydantic models for structured evidence collection
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from src.models.evidence_models import EvidenceItem

# ===== Common Context Steps =====
class ContextAnalysis(BaseModel):
    global_arrangement: str = Field(description="전체적인 배치 및 주변 상태 관찰 결과")
    fire_pattern: str = Field(description="화재 패턴 및 그을음의 방향성 관찰 결과")

class LocationMapping(BaseModel):
    identified_location: str = Field(description="확대 부위의 정확한 위치 특정 결과")

class Identification(BaseModel):
    crop_description: str = Field(description="확대 부위에서 식별된 주요 객체 및 상태 설명")

# ===== Specialist Specific Measurement Models =====

class TrackingTerminalMeasurement(BaseModel):
    inter_pole_gap_observation: str = Field(description="단자 사이 절연 구간의 탄화 경로 여부 및 형태")
    surface_erosion_graphitization: str = Field(description="탄화 부위의 침식(Erosion) 또는 흑연화(Graphitization) 징후")
    overall_melting_state: str = Field(description="단자대 전체의 용융 또는 변형 양상")

class TrackingPlugMeasurement(BaseModel):
    pin_face_base_observation: str = Field(description="핀 사이 바닥면(Face)의 상태 및 탄화물 형성 여부")
    carbon_bridge_formation: str = Field(description="양극을 잇는 명확한 탄화 다리(Bridge) 존재 여부")
    metallic_luster_check: str = Field(description="탄화물에서의 금속성/흑연 광택 관찰 결과")

class TrackingPCBMeasurement(BaseModel):
    inter_trace_path_observation: str = Field(description="패턴 사이의 탄화 경로 또는 이물질 형성 여부")
    dendrite_growth_check: str = Field(description="수지상 성장(Dendrite) 또는 거미줄형 금속 흔적 식별 결과")
    component_explosion_mark: str = Field(description="부품 폭발로 인한 방사형 그을음 또는 단순 변색 여부")

# ===== Final Evidence Results =====

class TrackingTerminalEvidenceResult(BaseModel):
    """Tracking Terminal Specialist 분석 결과 (6-Step Analysis)"""
    step1_context_analysis: ContextAnalysis
    step2_location_mapping: LocationMapping
    step3_crop_identification: Identification
    step4_geometric_measurement: TrackingTerminalMeasurement
    step5_extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")

    @property
    def visual_description(self) -> str:
        return f"{self.step4_geometric_measurement.inter_pole_gap_observation} | {self.step4_geometric_measurement.surface_erosion_graphitization}"
    
    @property
    def verdict(self) -> str:
        return "판독 보류 (Evidence Collected)"
    
    @property
    def confidence(self) -> int:
        return 0
    
    @property
    def reasoning(self) -> str:
        return "자세한 증거 목록이 생성되었습니다."

class TrackingPlugEvidenceResult(BaseModel):
    """Tracking Plug Specialist 분석 결과 (6-Step Analysis)"""
    step1_context_analysis: ContextAnalysis
    step2_location_mapping: LocationMapping
    step3_crop_identification: Identification
    step4_geometric_measurement: TrackingPlugMeasurement
    step5_extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")

    @property
    def visual_description(self) -> str:
        return f"{self.step4_geometric_measurement.pin_face_base_observation} | {self.step4_geometric_measurement.carbon_bridge_formation}"
    
    @property
    def verdict(self) -> str:
        return "판독 보류 (Evidence Collected)"
    
    @property
    def confidence(self) -> int:
        return 0
    
    @property
    def reasoning(self) -> str:
        return "자세한 증거 목록이 생성되었습니다."

class TrackingPCBEvidenceResult(BaseModel):
    """Tracking PCB Specialist 분석 결과 (6-Step Analysis)"""
    step1_context_analysis: ContextAnalysis
    step2_location_mapping: LocationMapping
    step3_crop_identification: Identification
    step4_geometric_measurement: TrackingPCBMeasurement
    step5_extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")

    @property
    def visual_description(self) -> str:
        return f"{self.step4_geometric_measurement.inter_trace_path_observation} | {self.step4_geometric_measurement.dendrite_growth_check}"
    
    @property
    def verdict(self) -> str:
        return "판독 보류 (Evidence Collected)"
    
    @property
    def confidence(self) -> int:
        return 0
    
    @property
    def reasoning(self) -> str:
        return "자세한 증거 목록이 생성되었습니다."
