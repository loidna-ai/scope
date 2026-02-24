"""
Wire Expert Common Models
공통 Pydantic 모델 (Necking / Deform 두 전문가가 공유하는 기하학적 측정 구조)
"""
from pydantic import BaseModel, Field


class Zone1Reference(BaseModel):
    reference_shaft_shape_observation: str = Field(
        description=(
            "기준 도체 영역의 기하학적 윤곽(Geometric Profile) 관찰 결과. "
            "사실 있는 그대로 서술. (접두어 라벨 없이)"
        )
    )
    surface_visual_check: str = Field(
        description=(
            "기준 도체 영역의 표면 상태 관찰 결과. "
            "사실 있는 그대로 서술. (접두어 라벨 없이)"
        )
    )


class Zone2Transition(BaseModel):
    width_change_observation: str = Field(
        description=(
            "기준 도체에서 최선단으로 이어지는 폭(Width)의 물리적 변화 양상. "
            "사실 있는 그대로 서술. (접두어 라벨 없이)"
        )
    )
    boundary_visual_check: str = Field(
        description=(
            "정상 부위와 손상 부위(또는 끝단) 사이의 경계면(Boundary) 관찰 결과. "
            "사실 있는 그대로 서술. (접두어 라벨 없이)"
        )
    )


class Zone3Apex(BaseModel):
    terminal_shape_observation: str = Field(
        description=(
            "최선단(끝단부)의 기하학적 형상(Geometric Shape) 관찰 결과. "
            "사실 있는 그대로 서술. (접두어 라벨 없이)"
        )
    )
    terminal_width_comparison: str = Field(
        description=(
            "최선단(끝단부)의 최대 너비를 기준 도체(Reference Shaft)와 비교한 결과. "
            "사실 있는 그대로 서술. (접두어 라벨 없이)"
        )
    )
    strand_state_observation: str = Field(
        description=(
            "최선단(끝단부) 가닥들의 물리적 결합 상태 관찰 결과. "
            "사실 있는 그대로 서술. (접두어 라벨 없이)"
        )
    )


class Zone4MeltedMarksBeads(BaseModel):
    bead_scan: str = Field(
        description=(
            "이미지 전체에서 확인되는 용융 흔적의 위치, 형태, 개수. "
            "특이 용융 흔적 없음 시 '특이 용융 흔적 없음(None Found).', "
            "판독 불가 시 '식별 불가(Unidentifiable)' 및 사유. (접두어 라벨 없이)"
        )
    )


class GeometricMeasurement(BaseModel):
    """4-Zone 기하학적 측정 결과 (Necking / Deform 공통)"""
    zone1_reference_shaft: Zone1Reference
    zone2_transition_gradient: Zone2Transition
    zone3_terminal_apex: Zone3Apex
    zone4_melted_marks_beads: Zone4MeltedMarksBeads
