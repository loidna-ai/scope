"""
Hotspot Detector Models
Pydantic models for structured output from hotspot detection
"""
from pydantic import BaseModel, Field, model_validator, field_validator
from typing import List, Optional, Dict


class BoundingBox2D(BaseModel):
    """2D Bounding Box (정규화 좌표 0-1000)"""
    ymin: int = Field(ge=0, le=1000, description="Y 최소값 (정규화)")
    xmin: int = Field(ge=0, le=1000, description="X 최소값 (정규화)")
    ymax: int = Field(ge=0, le=1000, description="Y 최대값 (정규화)")
    xmax: int = Field(ge=0, le=1000, description="X 최대값 (정규화)")
    
    @model_validator(mode='before')
    @classmethod
    def validate_input(cls, data):
        """하위 호환성: 배열 형식 입력도 객체로 변환"""
        if isinstance(data, list) and len(data) == 4:
            # 배열 형식: [ymin, xmin, ymax, xmax]
            return {"ymin": data[0], "xmin": data[1], "ymax": data[2], "xmax": data[3]}
        # dict 형식이거나 이미 인스턴스인 경우 그대로 반환
        return data
    
    @model_validator(mode='after')
    def check_coordinates_logic(self) -> 'BoundingBox2D':
        """좌표 논리 검증: ymin < ymax, xmin < xmax"""
        if self.ymin >= self.ymax:
            raise ValueError(
                f"Invalid box coordinates: ymin ({self.ymin}) must be less than ymax ({self.ymax})"
            )
        if self.xmin >= self.xmax:
            raise ValueError(
                f"Invalid box coordinates: xmin ({self.xmin}) must be less than xmax ({self.xmax})"
            )
        return self


class Hotspot(BaseModel):
    """개별 Hotspot 정보"""
    id: int = Field(ge=1, description="Hotspot 고유 ID")
    
    image_index: int = Field(ge=1, description="해당 Hotspot이 발견된 입력 이미지의 순번 (1부터 시작)")
    
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
    
    # 선택적 필드
    reason_for_selection: Optional[str] = Field(
        default=None,
        description="선정 근거 (이미지 정확도 및 관찰된 사실 기반)"
    )
    
    suspected_feature: Optional[str] = Field(
        default=None,
        description="물리적 특징 묘사 (예: Spherical Bead, 70% Carbonized Resin 등)"
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
    
    # 선택적 필드
    scene_overview: Optional[str] = Field(
        default=None,
        description="현장 전체의 열적 변형 패턴 및 대상체에 대한 객관적 요약 (사실 중심)"
    )
    
    detailed_observations: Optional[List[str]] = Field(
        default=None,
        description="객체별 형태학적 정밀 묘사 리스트"
    )

    reasoning: Optional[str] = Field(
        default=None,
        description="탐지 과정에 대한 논리적 추론 (Chain of Thought)"
    )


class UnifiedHotspot(BaseModel):
    """다중 이미지/다각도(Deep) 및 다중 지점(Wide) 분석을 위한 통합 Hotspot 패키지"""
    id: int = Field(description="통합 Hotspot 고유 ID")
    
    source_images: List[str] = Field(
        description="이 객체가 발견된 원본 이미지 경로 목록"
    )
    
    boxes: Dict[str, BoundingBox2D] = Field(
        description="이미지 경로별 2D Bounding Box 매핑 (키: 이미지 경로, 값: BBox)"
    )
    
    severity_score: int = Field(
        ge=0, le=100,
        description="통합된 대표 심각도 점수"
    )
    
    location_description: str = Field(
        description="종합된 위치 및 구역 설명"
    )
    
    visual_evidence: str = Field(
        description="모든 각도의 시각적 증거를 종합한 설명"
    )
    
    raw_hotspot_ids: List[int] = Field(
        default_factory=list,
        description="병합된 원본 Hotspot ID 목록"
    )
    
    # 선택적 / 후속 노드에서 채워질 필드
    roi_image_paths: Dict[str, str] = Field(
        default_factory=dict,
        description="이미지 경로별 Crop된 ROI 임시 파일 경로 매핑"
    )
    
    component_type: Optional[str] = Field(
        default=None,
        description="부품 분류 결과 (preprocessor에서 설정)"
    )
    
    is_preprocessed: bool = Field(
        default=False, 
        description="전처리 완료 여부 플래그",
        alias="_preprocessed"
    )

    model_config = {
        "populate_by_name": True
    }

    @model_validator(mode='after')
    def check_boxes_consistency(self) -> 'UnifiedHotspot':
        """이미지 소스와 박스 매핑의 일관성 검증"""
        for img in self.source_images:
            if img not in self.boxes:
                raise ValueError(f"Missing bounding box for image: {img}")
        return self


class IdentityFusionResult(BaseModel):
    """Identity Fusion 과정의 전체 결과"""
    reasoning: str = Field(
        description="객체 그룹핑(Identity Fusion)에 대한 논리적 추론"
    )
    
    unified_hotspots: List[UnifiedHotspot] = Field(
        default_factory=list,
        description="병합된 통합 Hotspot 리스트"
    )
