"""
Deform Expert Evidence Models
Pydantic models for structured evidence collection
"""
from pydantic import BaseModel, Field
from typing import List, Optional

class Zone1Reference(BaseModel):
    reference_shaft_shape_observation: str = Field(description="기준 도체 영역의 기하학적 윤곽(Geometric Profile) 관찰 결과. 사실 있는 그대로 서술. (접두어 라벨 없이)")
    surface_visual_check: str = Field(description="기준 도체 영역의 표면 상태 관찰 결과. 사실 있는 그대로 서술. (접두어 라벨 없이)")

class Zone2Transition(BaseModel):
    width_change_observation: str = Field(description="기준 도체에서 최선단으로 이어지는 폭(Width)의 물리적 변화 양상. 사실 있는 그대로 서술. (접두어 라벨 없이)")
    boundary_visual_check: str = Field(description="정상 부위와 손상 부위(또는 끝단) 사이의 경계면(Boundary) 관찰 결과. 사실 있는 그대로 서술. (접두어 라벨 없이)")

class Zone3Apex(BaseModel):
    terminal_shape_observation: str = Field(description="최선단(끝단부)의 기하학적 형상(Geometric Shape) 관찰 결과. 사실 있는 그대로 서술. (접두어 라벨 없이)")
    terminal_width_comparison: str = Field(description="최선단(끝단부)의 최대 너비를 기준 도체(Reference Shaft)와 비교한 결과. 사실 있는 그대로 서술. (접두어 라벨 없이)")
    strand_state_observation: str = Field(description="최선단(끝단부) 가닥들의 물리적 결합 상태 관찰 결과. 사실 있는 그대로 서술. (접두어 라벨 없이)")

class Zone4MeltedMarksBeads(BaseModel):
    bead_scan: str = Field(description="이미지 전체에서 확인되는 용융 흔적의 위치, 형태, 개수. 특이 용융 흔적 없음 시 '특이 용융 흔적 없음(None Found).', 판독 불가 시 '식별 불가(Unidentifiable)' 및 사유. (접두어 라벨 없이)")

class GeometricMeasurement(BaseModel):
    zone1_reference_shaft: Zone1Reference
    zone2_transition_gradient: Zone2Transition
    zone3_terminal_apex: Zone3Apex
    zone4_melted_marks_beads: Zone4MeltedMarksBeads

class LogicContrast(BaseModel):
    logic_refuting: str = Field(description="Evidence refuting deform")
    logic_supporting: str = Field(description="Evidence supporting deform")

class FinalVerdict(BaseModel):
    conclusion: str = Field(description="압착, 손상 | 압착, 손상 의심 | 압착, 손상 아님 | 판독 불가")
    confidence_score: int = Field(ge=0, le=100)
    final_reasoning: str = Field(description="Summary of reasoning")

class DeformEvidenceResult(BaseModel):
    step1_context_analysis: dict = Field(default_factory=dict)
    step2_location_mapping: dict = Field(default_factory=dict)
    step3_crop_identification: dict = Field(default_factory=dict)
    step4_geometric_measurement: GeometricMeasurement
    step5_logic_contrast: LogicContrast
    step6_verdict: FinalVerdict

class SupervisorVerdict(BaseModel):
    final_conclusion: str = Field(description="압착, 손상 | 압착, 손상 의심 | 압착, 손상 아님 | 판독 불가")
    final_confidence: int = Field(ge=0, le=100, description="Final confidence score (0-100)")
    key_evidence_summary: str = Field(description="Summary of key facts driving the decision")
    reasoning_process: str = Field(description="Synthesis of worker reports and conflict resolution")
