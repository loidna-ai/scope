"""
크롭 노드
Morphological Gradient 기반으로 단락흔 영역을 탐지하고 크롭합니다.
"""
from typing import Dict, Any
import cv2
import numpy as np
from src.state import GraphState
import config

class ImageCropper:
    """
    Morphological Gradient 기반 스마트 크롭퍼
    
    핵심 원리:
    1. Morphological Gradient: 이미지의 밝기 변화량(엣지+질감)을 계산
    2. Dilation (팽창): 흩어진 엣지들을 하나의 큰 덩어리로 뭉침
    3. Largest Contour: 가장 큰 덩어리를 찾아 크롭
    """
    
    def __init__(self):
        """크롭퍼 초기화"""
        pass
    
    def crop(self, img: np.ndarray) -> np.ndarray:
        """
        이미지에서 단락흔 영역을 탐지하고 크롭합니다.
        
        Args:
            img: 입력 이미지 (BGR 형식)
        
        Returns:
            크롭된 이미지
        """
        try:
            # 1. 전처리: 그레이스케일 변환
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            # 2. 형태학적 그래디언트 (Morphological Gradient) 계산
            kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT, 
                config.MORPH_KERNEL_SIZE
            )
            gradient = cv2.morphologyEx(gray, cv2.MORPH_GRADIENT, kernel)
            
            # 3. 이진화 (Binarization)
            _, binary = cv2.threshold(
                gradient, 0, 255, 
                cv2.THRESH_BINARY + cv2.THRESH_OTSU
            )
            
            # 4. 팽창 (Dilation)
            expand_kernel = cv2.getStructuringElement(
                cv2.MORPH_RECT,
                config.DILATION_KERNEL_SIZE
            )
            closed = cv2.dilate(binary, expand_kernel, iterations=config.DILATION_ITERATIONS)
            
            # 5. 가장 큰 덩어리(Contour) 찾기
            contours, _ = cv2.findContours(
                closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            if not contours:
                return self._center_crop(img)
            
            # 면적 기준으로 정렬하여 가장 큰 놈 선택
            largest_contour = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest_contour)
            
            # 6. 유효성 검사 (너무 작거나 전체를 다 덮으면 무시)
            img_h, img_w = img.shape[:2]
            if (w * h) < (img_w * img_h) * config.CROP_MIN_AREA_RATIO:
                return self._center_crop(img)
            
            # 7. 패딩 추가 및 크롭
            pad = config.CROP_PADDING
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(img_w, x + w + pad)
            y2 = min(img_h, y + h + pad)
            
            return img[y1:y2, x1:x2]
        
        except Exception as e:
            # 에러 발생 시 중앙 크롭으로 Fallback
            return self._center_crop(img)
    
    def _center_crop(self, img: np.ndarray) -> np.ndarray:
        """
        탐지 실패 시 안전하게 중앙을 자르는 Fallback
        
        Args:
            img: 입력 이미지
        
        Returns:
            중앙 크롭된 이미지
        """
        h, w = img.shape[:2]
        crop_size = min(h, w) // 2
        cx, cy = w // 2, h // 2
        
        x1 = max(0, cx - crop_size // 2)
        y1 = max(0, cy - crop_size // 2)
        x2 = min(w, cx + crop_size // 2)
        y2 = min(h, cy + crop_size // 2)
        
        return img[y1:y2, x1:x2]

def crop_node(state: GraphState) -> Dict[str, Any]:
    """
    크롭 노드
    
    Args:
        state: 그래프 상태
    
    Returns:
        업데이트할 상태 필드 (Partial State)
    """
    if state.get("original_image") is None:
        return {
            "errors": ["크롭 실패: 원본 이미지가 없습니다."]
        }
    
    try:
        cropper = ImageCropper()
        cropped_image = cropper.crop(state["original_image"])
        
        return {
            "cropped_image": cropped_image
        }
    except Exception as e:
        error_msg = f"크롭 실패: {str(e)}"
        return {
            "errors": [error_msg]
        }

