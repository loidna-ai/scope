"""
Contact Expert Evidence Models
Pydantic models for structured evidence collection
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from src.models.evidence_models import EvidenceItem

# ===== Splice Specialist Models (6-Step Analysis) =====

class Zone1ReferenceConductorArea(BaseModel):
    conductor_shape: str = Field(description="기준 도체 영역의 기하학적 윤곽(Geometric Profile) 관찰 결과. 사실 있는 그대로 서술.")
    conductor_discoloration: str = Field(description="기준 도체 영역의 표면 변색 및 경계 양상 관찰 결과. 사실 있는 그대로 서술.")

class Zone2TransitionArea(BaseModel):
    transition_shape: str = Field(description="이행 구간의 물리적 변형 및 피복 소실 형태 관찰 결과. 사실 있는 그대로 서술.")
    transition_discoloration: str = Field(description="이행 구간의 열적 그라데이션 및 경계 양상 관찰 결과. 사실 있는 그대로 서술.")

class Zone3SpliceArea(BaseModel):
    splice_shape: str = Field(description="접속부 구성 요소의 체결 무결성 및 표면 물리적 형상 관찰 결과. 사실 있는 그대로 서술.")
    splice_discoloration: str = Field(description="접속부 표면의 열적 변색 및 경계 양상 관찰 결과. 사실 있는 그대로 서술.")

class Zone3TerminalArea(BaseModel):
    terminal_shape: str = Field(description="터미널 구성 요소의 체결 무결성 및 표면 물리적 형상 관찰 결과. 사실 있는 그대로 서술.")
    terminal_discoloration: str = Field(description="터미널 표면의 산화 패턴 및 열적 변색 관찰 결과. 사실 있는 그대로 서술.")

class Zone4MeltedMarksBeads(BaseModel):
    bead_scan: str = Field(description="이미지 전체에서 확인되는 용융 흔적의 위치, 형태, 개수. 특이 용융 흔적 없음 시 '특이 용융 흔적 없음(None Found).', 판독 불가 시 '식별 불가(Unidentifiable)' 및 사유.")

class GeometricMeasurement(BaseModel):
    zone1_reference_conductor_area: Zone1ReferenceConductorArea
    zone2_transition_area: Zone2TransitionArea
    zone3_splice_area: Zone3SpliceArea
    zone4_melted_marks_beads: Zone4MeltedMarksBeads

class TerminalGeometricMeasurement(BaseModel):
    zone1_reference_conductor_area: Zone1ReferenceConductorArea
    zone2_transition_area: Zone2TransitionArea
    zone3_terminal_area: Zone3TerminalArea
    zone4_melted_marks_beads: Zone4MeltedMarksBeads



class SpliceEvidenceResult(BaseModel):
    """Splice Specialist 분석 결과 (6-Step Analysis)"""
    step1_context_analysis: dict = Field(default_factory=dict, description="전체 문맥 관찰 결과")
    step2_location_mapping: dict = Field(default_factory=dict, description="확대 부위 위치 특정 결과")
    step3_crop_identification: dict = Field(default_factory=dict, description="확대 부위 식별 결과")
    step4_geometric_measurement: GeometricMeasurement
    step5_extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")
    
    # Legacy compatibility properties
    @property
    def visual_description(self) -> str:
        """하위 호환성을 위한 visual_description 추출"""
        # step4의 주요 관찰 사항을 종합
        zone1 = self.step4_geometric_measurement.zone1_reference_conductor_area
        zone3 = self.step4_geometric_measurement.zone3_splice_area
        zone4 = self.step4_geometric_measurement.zone4_melted_marks_beads
        
        desc_parts = [
            f"Zone 1 (기준 도체): {zone1.conductor_shape[:100]}...",
            f"Zone 3 (접속부): {zone3.splice_shape[:100]}...",
            f"Zone 4 (용융 흔적): {zone4.bead_scan[:100]}..."
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

# ===== Terminal Specialist Models (6-Step Analysis) =====

class TerminalEvidenceResult(BaseModel):
    """Terminal Specialist 분석 결과 (6-Step Analysis)"""
    step1_context_analysis: dict = Field(default_factory=dict, description="전체 문맥 관찰 결과")
    step2_location_mapping: dict = Field(default_factory=dict, description="확대 부위 위치 특정 결과")
    step3_crop_identification: dict = Field(default_factory=dict, description="확대 부위 식별 결과")
    step4_geometric_measurement: TerminalGeometricMeasurement
    step5_extracted_evidence: List[EvidenceItem] = Field(description="정밀 측정된 시각적 증거 객체 목록")
    
    # Legacy compatibility properties
    @property
    def visual_description(self) -> str:
        """하위 호환성을 위한 visual_description 추출"""
        zone1 = self.step4_geometric_measurement.zone1_reference_conductor_area
        zone3 = self.step4_geometric_measurement.zone3_terminal_area
        zone4 = self.step4_geometric_measurement.zone4_melted_marks_beads
        
        desc_parts = [
            f"Zone 1 (기준 도체): {zone1.conductor_shape[:100]}...",
            f"Zone 3 (터미널): {zone3.terminal_shape[:100]}...",
            f"Zone 4 (용융 흔적): {zone4.bead_scan[:100]}..."
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

class PlugEvidenceResult(BaseModel):
    """Plug Specialist 분석 결과"""
    visual_description: str = Field(description="시각적 특징 관찰 결과")
    verdict: str = Field(description="접촉 불량 / 외부 화재 / 판단 불가")
    confidence: int = Field(ge=0, le=100, description="신뢰도 점수 (0-100)")
    reasoning: str = Field(description="판정 근거")
