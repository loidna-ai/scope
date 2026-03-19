"""
좌표 정규화 유틸리티 (Coordinate Normalization Utility)
다중 이미지 해상도 파편화 문제를 해결하기 위해,
각기 다른 해상도를 가진 이미지들의 절대 좌표를 0~1000 사이의 상대 좌표계로 변환하거나 복원합니다.
Gemini Vision의 기본 BBox 포맷(0~1000)과 시스템 간소화를 위해 사용됩니다.
"""

import math
from typing import Dict, Union, TypedDict


class BBox(TypedDict):
    """0~1000 상대 좌표계 또는 절대 좌표계의 Bounding Box 정의"""
    ymin: Union[int, float]
    xmin: Union[int, float]
    ymax: Union[int, float]
    xmax: Union[int, float]


def normalize_bbox(bbox: BBox, img_width: int, img_height: int) -> BBox:
    """
    절대 좌표(Absolute) 기반의 BBox를 0~1000 상대 좌표계(Normalized)로 변환합니다.
    
    Args:
        bbox (BBox): {"ymin": val, "xmin": val, "ymax": val, "xmax": val}
        img_width (int): 원본 이미지의 너비
        img_height (int): 원본 이미지의 높이
        
    Returns:
        BBox: 정규화된 좌표 {"ymin": 0~1000, "xmin": 0~1000, ...}
    """
    if img_width <= 0 or img_height <= 0:
        return {**bbox}  # Return a shallow copy to ensure immutability
        
    def _clamp(val: float, min_val: int = 0, max_val: int = 1000) -> int:
        return max(min_val, min(max_val, int(math.floor(val))))

    # Create new dict to ensure immutability
    return {
        "ymin": _clamp((bbox.get("ymin", 0) / img_height) * 1000),
        "xmin": _clamp((bbox.get("xmin", 0) / img_width) * 1000),
        "ymax": _clamp((bbox.get("ymax", 0) / img_height) * 1000),
        "xmax": _clamp((bbox.get("xmax", 0) / img_width) * 1000)
    }


def denormalize_bbox(bbox: BBox, img_width: int, img_height: int) -> BBox:
    """
    0~1000 상대 좌표계(Normalized)의 BBox를 주어진 해상도에 맞춰 절대 좌표(Absolute)로 복원합니다.
    
    Args:
        bbox (BBox): {"ymin": 0~1000, "xmin": 0~1000, "ymax": 0~1000, "xmax": 0~1000}
        img_width (int): 복원할(원본) 이미지의 너비
        img_height (int): 복원할(원본) 이미지의 높이
        
    Returns:
        BBox: 절대 좌표 {"ymin": 0~H, "xmin": 0~W, ...}
    """
    if img_width <= 0 or img_height <= 0:
        return {**bbox} # Return a shallow copy to ensure immutability

    def _clamp(val: float, max_val: int) -> int:
        return max(0, min(max_val, int(math.floor(val))))

    # Create new dict to ensure immutability
    return {
        "ymin": _clamp((bbox.get("ymin", 0) / 1000) * img_height, img_height),
        "xmin": _clamp((bbox.get("xmin", 0) / 1000) * img_width, img_width),
        "ymax": _clamp((bbox.get("ymax", 0) / 1000) * img_height, img_height),
        "xmax": _clamp((bbox.get("xmax", 0) / 1000) * img_width, img_width)
    }
