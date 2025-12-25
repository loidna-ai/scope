"""
메트릭스 노드
형태학적 분석을 수행하여 원형도, 고형도, 면적 등을 추출합니다.
"""
from typing import Dict, Any
import cv2
import numpy as np
from skimage import measure
from src.state import GraphState


class MorphologyAnalyzer:
    """형태학적 분석 클래스"""
    
    def analyze(self, img: np.ndarray) -> tuple[dict, np.ndarray]:
        """
        이미지의 형태학적 특성을 분석합니다.
        
        Args:
            img: 입력 이미지 (BGR 형식)
        
        Returns:
            (metrics, binary_mask) 튜플
            - metrics: 형태학적 메트릭스 딕셔너리 (circularity, solidity, area)
            - binary_mask: 이진화된 마스크 이미지
        """
        # 그레이스케일 변환
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # 이진화
        _, binary = cv2.threshold(
            gray, 0, 255, 
            cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        
        # 레이블링 및 영역 속성 추출
        label_img = measure.label(binary)
        regions = measure.regionprops(label_img)
        
        # 기본 메트릭스 초기화
        metrics = {
            "circularity": 0.0,
            "solidity": 0.0,
            "area": 0
        }
        
        if regions:
            # 가장 큰 영역 선택
            largest = max(regions, key=lambda r: r.area)
            
            # 둘레 계산 (0보다 큰 값 보장)
            perimeter = largest.perimeter if largest.perimeter > 0 else 1
            
            # 원형도 계산: 4π * area / perimeter²
            metrics["circularity"] = round(
                (4 * np.pi * largest.area) / (perimeter ** 2), 
                3
            )
            
            # 고형도 (Solidity): area / convex_area
            metrics["solidity"] = round(largest.solidity, 3)
            
            # 면적
            metrics["area"] = int(largest.area)
        
        return metrics, binary


def metrics_node(state: GraphState) -> Dict[str, Any]:
    """
    메트릭스 노드
    
    Args:
        state: 그래프 상태
    
    Returns:
        업데이트할 상태 필드 (Partial State)
    """
    if state.get("enhanced_image") is None:
        return {
            "errors": ["메트릭스 분석 실패: 향상된 이미지가 없습니다."]
        }
    
    try:
        analyzer = MorphologyAnalyzer()
        metrics, binary_mask = analyzer.analyze(state["enhanced_image"])
        
        return {
            "binary_mask": binary_mask,
            "metrics": metrics
        }
    except Exception as e:
        error_msg = f"메트릭스 분석 실패: {str(e)}"
        return {
            "errors": [error_msg]
        }

