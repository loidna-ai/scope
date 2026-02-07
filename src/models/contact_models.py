"""
Contact Expert Evidence Models
Pydantic models for structured evidence collection
"""
from pydantic import BaseModel, Field
from typing import List, Optional

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

class LogicContrast(BaseModel):
    logic_refuting: str = Field(description="관찰된 특징 중 '접촉불량'이 아님을 시사하는 반박 논리 서술")
    logic_supporting: str = Field(description="관찰된 특징 중 '접촉불량'을 지지하는 강력한 증거와 논리 서술")

class FinalVerdict(BaseModel):
    conclusion: str = Field(description="접촉불량 | 접촉불량 의심 | 접촉불량 아님 | 판독 불가")
    confidence_score: int = Field(ge=0, le=100, description="신뢰도 점수 (0-100)")
    final_reasoning: str = Field(description="STEP 5의 논리 대결을 종합하여 최종 결론을 내린 결정적 이유 요약")

class SpliceEvidenceResult(BaseModel):
    """Splice Specialist 분석 결과 (6-Step Analysis)"""
    step1_context_analysis: dict = Field(default_factory=dict, description="전체 문맥 관찰 결과")
    step2_location_mapping: dict = Field(default_factory=dict, description="확대 부위 위치 특정 결과")
    step3_crop_identification: dict = Field(default_factory=dict, description="확대 부위 식별 결과")
    step4_geometric_measurement: GeometricMeasurement
    step5_logic_contrast: LogicContrast
    step6_verdict: FinalVerdict
    
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
        """하위 호환성을 위한 verdict 추출"""
        conclusion = self.step6_verdict.conclusion
        # 매핑: 프롬프트의 conclusion을 기존 verdict 형식으로 변환
        if conclusion == "접촉불량":
            return "접촉 불량"
        elif conclusion == "접촉불량 의심":
            return "판단 불가"  # 의심은 판단 불가로 분류
        elif conclusion == "접촉불량 아님":
            return "외부 화재"
        else:  # 판독 불가
            return "판단 불가"
    
    @property
    def confidence(self) -> int:
        """하위 호환성을 위한 confidence 추출"""
        return self.step6_verdict.confidence_score
    
    @property
    def reasoning(self) -> str:
        """하위 호환성을 위한 reasoning 추출"""
        return self.step6_verdict.final_reasoning

# ===== Terminal Specialist Models (6-Step Analysis) =====

class TerminalEvidenceResult(BaseModel):
    """Terminal Specialist 분석 결과 (6-Step Analysis)"""
    step1_context_analysis: dict = Field(default_factory=dict, description="전체 문맥 관찰 결과")
    step2_location_mapping: dict = Field(default_factory=dict, description="확대 부위 위치 특정 결과")
    step3_crop_identification: dict = Field(default_factory=dict, description="확대 부위 식별 결과")
    step4_geometric_measurement: TerminalGeometricMeasurement
    step5_logic_contrast: LogicContrast
    step6_verdict: FinalVerdict
    
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
        """하위 호환성을 위한 verdict 추출"""
        conclusion = self.step6_verdict.conclusion
        if conclusion == "접촉불량":
            return "접촉 불량"
        elif conclusion == "접촉불량 의심":
            return "판단 불가"
        elif conclusion == "접촉불량 아님":
            return "외부 화재"
        else:  # 판독 불가
            return "판단 불가"
    
    @property
    def confidence(self) -> int:
        """하위 호환성을 위한 confidence 추출"""
        return self.step6_verdict.confidence_score
    
    @property
    def reasoning(self) -> str:
        """하위 호환성을 위한 reasoning 추출"""
        return self.step6_verdict.final_reasoning

class PlugEvidenceResult(BaseModel):
    """Plug Specialist 분석 결과"""
    visual_description: str = Field(description="시각적 특징 관찰 결과")
    verdict: str = Field(description="접촉 불량 / 외부 화재 / 판단 불가")
    confidence: int = Field(ge=0, le=100, description="신뢰도 점수 (0-100)")
    reasoning: str = Field(description="판정 근거")

class SupervisorVerdict(BaseModel):
    """Supervisor 종합 판정 결과"""
    final_conclusion: str = Field(description="접촉불량 유력 (High) / 접촉불량 의심 (Medium) / 단락 또는 외부 화재 (Low)")
    final_confidence: int = Field(ge=0, le=100, description="Final confidence score (0-100)")
    key_evidence_summary: str = Field(description="Summary of key facts driving the decision")
    reasoning_process: str = Field(description="Synthesis of worker reports and conflict resolution")
