"""
향상 노드
Real-ESRGAN을 사용하여 이미지를 4배 초해상도로 향상시킵니다.
"""
import os
import cv2
import numpy as np
import torch
from basicsr.archs.rrdbnet_arch import RRDBNet
from realesrgan import RealESRGANer
from src.state import GraphState
import config
import logging

logger = logging.getLogger(__name__)


class ImageEnhancer:
    """Real-ESRGAN 기반 이미지 향상 클래스"""
    
    def __init__(self, model_path: str = None):
        """
        향상기 초기화
        
        Args:
            model_path: 모델 가중치 경로 (기본값: config.MODEL_PATH)
        """
        if model_path is None:
            model_path = config.MODEL_PATH
        
        self.upscaler = self._load_model(model_path)
    
    def _load_model(self, model_path: str) -> RealESRGANer:
        """
        Real-ESRGAN 모델을 로드합니다.
        
        Args:
            model_path: 모델 가중치 경로
        
        Returns:
            RealESRGANer 인스턴스
        """
        # 모델 디렉토리 생성
        model_dir = os.path.dirname(model_path)
        if model_dir and not os.path.exists(model_dir):
            os.makedirs(model_dir, exist_ok=True)
        
        # 모델이 없으면 다운로드
        if not os.path.exists(model_path):
            logger.info(f"모델 다운로드 중: {model_path}")
            url = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth'
            torch.hub.download_url_to_file(url, model_path)
        
        # 모델 아키텍처 정의
        model = RRDBNet(
            num_in_ch=3, 
            num_out_ch=3, 
            num_feat=64, 
            num_block=23, 
            num_grow_ch=32, 
            scale=config.SR_SCALE
        )
        
        # 디바이스 설정
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # RealESRGANer 초기화
        return RealESRGANer(
            scale=config.SR_SCALE,
            model_path=model_path,
            model=model,
            tile=0,
            pre_pad=0,
            half=(device.type == 'cuda'),
            device=device
        )
    
    def upscale(self, img: np.ndarray) -> np.ndarray:
        """
        이미지를 초해상도로 향상시킵니다.
        
        Args:
            img: 입력 이미지 (BGR 형식)
        
        Returns:
            향상된 이미지 (4배 확대)
        """
        try:
            output, _ = self.upscaler.enhance(img, outscale=config.SR_SCALE)
            return output
        except Exception as e:
            logger.warning(f"Upscale Error: {e}")
            # Fallback: 단순 리사이즈
            h, w = img.shape[:2]
            return cv2.resize(img, (w * config.SR_SCALE, h * config.SR_SCALE))


def enhancement_node(state: GraphState) -> dict:
    """
    향상 노드
    
    Args:
        state: 그래프 상태
    
    Returns:
        업데이트할 상태 필드 (Partial State)
    """
    if state.get("cropped_image") is None:
        return {
            "errors": ["향상 실패: 크롭된 이미지가 없습니다."]
        }
    
    try:
        enhancer = ImageEnhancer()
        input_img = state["cropped_image"]
        
        # 입력 크기 저장
        input_h, input_w = input_img.shape[:2]
        
        # 향상 수행
        enhanced_img = enhancer.upscale(input_img)
        
        # 크기 검증
        output_h, output_w = enhanced_img.shape[:2]
        expected_h = input_h * config.SR_SCALE
        expected_w = input_w * config.SR_SCALE
        
        # 검증 실패 시 경고 로그
        if abs(output_h - expected_h) > 1 or abs(output_w - expected_w) > 1:
            logger.warning(
                f"크기 검증 실패: 예상 ({expected_h}x{expected_w}), "
                f"실제 ({output_h}x{output_w})"
            )
        
        return {
            "enhanced_image": enhanced_img
        }
    except Exception as e:
        error_msg = f"향상 실패: {str(e)}"
        return {
            "errors": [error_msg]
        }

