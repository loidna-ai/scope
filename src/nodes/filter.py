"""
필터 노드
CLAHE (Contrast Limited Adaptive Histogram Equalization) 필터를 적용합니다.
"""
from typing import Dict, Any
import cv2
import numpy as np
from src.state import GraphState
import config


class TextureFilter:
    """텍스처 강조 필터 클래스"""
    
    @staticmethod
    def apply_clahe(img: np.ndarray) -> np.ndarray:
        """
        CLAHE 필터를 적용합니다.
        
        Args:
            img: 입력 이미지 (BGR 형식)
        
        Returns:
            필터 적용된 이미지 (BGR 형식)
        """
        # LAB 색공간으로 변환
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        
        # CLAHE 적용
        clahe = cv2.createCLAHE(
            clipLimit=config.CLAHE_CLIP_LIMIT,
            tileGridSize=config.CLAHE_TILE_GRID_SIZE
        )
        cl = clahe.apply(l)
        
        # LAB 색공간으로 병합 후 BGR로 변환
        limg = cv2.merge((cl, a, b))
        return cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)


def filter_node(state: GraphState) -> Dict[str, Any]:
    """
    필터 노드
    
    Args:
        state: 그래프 상태
    
    Returns:
        업데이트할 상태 필드 (Partial State)
    """
    if state.get("enhanced_image") is None:
        return {
            "errors": ["필터 적용 실패: 향상된 이미지가 없습니다."]
        }
    
    try:
        filtered_img = TextureFilter.apply_clahe(state["enhanced_image"])
        
        return {
            "filtered_image": filtered_img
        }
    except Exception as e:
        error_msg = f"필터 적용 실패: {str(e)}"
        return {
            "errors": [error_msg]
        }

