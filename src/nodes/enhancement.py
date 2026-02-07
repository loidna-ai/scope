"""
향상 노드
Real-ESRGAN을 사용하여 이미지를 2배 초해상도로 향상시킵니다.
"""
from typing import Dict, Any
import os
import cv2
import numpy as np
import torch
import torch
import logging

logger = logging.getLogger(__name__)

try:
    from basicsr.archs.rrdbnet_arch import RRDBNet
    from realesrgan import RealESRGANer
    HAS_REALESRGAN = True
except ImportError:
    HAS_REALESRGAN = False
    RealESRGANer = None
    RRDBNet = None
    logger.warning("RealESRGANer or BasicSR not available (ImportError). Image enhancement will use simple resizing.")

try:
    import onnxruntime as ort
    HAS_ONNX_RUNTIME = True
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
    try:
        available_providers = ort.get_available_providers()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:18","message":"ONNX Runtime import success","data":{"has_onnx_runtime":True,"available_providers":available_providers},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
except ImportError as e:
    HAS_ONNX_RUNTIME = False
    ort = None
    logger.debug("ONNX Runtime not available. ONNX-based acceleration will be disabled.")
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:28","message":"ONNX Runtime import failed","data":{"has_onnx_runtime":False,"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion
except Exception as e:
    HAS_ONNX_RUNTIME = False
    ort = None
    logger.debug(f"ONNX Runtime initialization failed: {e}")
    # #region agent log
    import json
    import time
    from pathlib import Path
    log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:38","message":"ONNX Runtime init failed","data":{"has_onnx_runtime":False,"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+"\n")
    except: pass
    # #endregion

from src.state import GraphState
import config
import threading

# 싱글톤 패턴: 모델을 한 번만 로드하고 재사용
_shared_upscaler = None
_upscaler_type = None  # "onnx" 또는 "pytorch"
_onnx_input_shape = None  # ONNX 모델 입력 크기 정보
_upscaler_lock = threading.Lock()
_onnx_inference_lock = threading.Lock()  # ONNX 추론 동시성 제어

class ImageEnhancer:
    """Real-ESRGAN 기반 이미지 향상 클래스 (싱글톤 패턴으로 모델 공유)
    
    하이브리드 접근 방식:
    - CUDA 사용 가능: PyTorch 방식 사용
    - DirectML 사용 가능: ONNX Runtime 방식 사용
    - CPU만 사용 가능: PyTorch 방식 사용
    """
    
    @staticmethod
    def _detect_available_backend():
        """
        사용 가능한 백엔드를 감지합니다.
        
        Returns:
            str: "cuda", "directml", 또는 "cpu"
        """
        # #region agent log
        import json
        import time
        from pathlib import Path
        log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:52","message":"_detect_available_backend entry","data":{"has_onnx_runtime":HAS_ONNX_RUNTIME,"cuda_available":torch.cuda.is_available()},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # CUDA 우선순위 1
        if torch.cuda.is_available():
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:60","message":"CUDA detected","data":{"backend":"cuda"},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            return "cuda"
        
        # DirectML 우선순위 2 (AMD GPU)
        if HAS_ONNX_RUNTIME:
            try:
                # DirectML provider 사용 가능 여부 확인
                available_providers = ort.get_available_providers()
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:68","message":"Checking DirectML providers","data":{"available_providers":available_providers,"has_dml":"DmlExecutionProvider" in available_providers},"timestamp":int(time.time()*1000)})+"\n")
                except: pass
                # #endregion
                if 'DmlExecutionProvider' in available_providers:
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:73","message":"DirectML detected","data":{"backend":"directml"},"timestamp":int(time.time()*1000)})+"\n")
                    except: pass
                    # #endregion
                    return "directml"
            except Exception as e:
                logger.debug(f"DirectML 감지 실패: {e}")
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:76","message":"DirectML detection failed","data":{"error":str(e)},"timestamp":int(time.time()*1000)})+"\n")
                except: pass
                # #endregion
        
        # CPU fallback
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"C","location":"enhancement.py:79","message":"CPU fallback","data":{"backend":"cpu"},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        return "cpu"
    
    def _preprocess_onnx(self, img: np.ndarray, target_h: int = None, target_w: int = None) -> tuple:
        """
        ONNX Runtime용 이미지 전처리
        
        Args:
            img: 입력 이미지 (BGR 형식, HWC)
            target_h: 목표 높이 (None이면 모델 입력 크기 사용)
            target_w: 목표 너비 (None이면 모델 입력 크기 사용)
            
        Returns:
            (전처리된 이미지 텐서, 원본 크기 정보, 패딩 정보)
        """
        original_h, original_w = img.shape[:2]
        
        # 모델이 요구하는 크기로 리사이즈 (고정 크기 모델 대응)
        if target_h is None or target_w is None:
            # 기본값: 모델이 요구하는 크기 (128x128)
            target_h = 128
            target_w = 128
        
        # 리사이즈 (비율 유지하면서 패딩 추가)
        scale = min(target_h / original_h, target_w / original_w)
        new_h = int(original_h * scale)
        new_w = int(original_w * scale)
        
        img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # 패딩 추가 (중앙 정렬)
        pad_top = (target_h - new_h) // 2
        pad_bottom = target_h - new_h - pad_top
        pad_left = (target_w - new_w) // 2
        pad_right = target_w - new_w - pad_left
        
        img_padded = cv2.copyMakeBorder(
            img_resized, pad_top, pad_bottom, pad_left, pad_right,
            cv2.BORDER_REPLICATE
        )
        
        # BGR -> RGB 변환
        img_rgb = cv2.cvtColor(img_padded, cv2.COLOR_BGR2RGB)
        
        # 0-255 -> 0-1 정규화
        img_normalized = img_rgb.astype(np.float32) / 255.0
        
        # HWC -> CHW 변환
        img_chw = img_normalized.transpose((2, 0, 1))
        
        # 배치 차원 추가: (C, H, W) -> (1, C, H, W)
        img_batch = np.expand_dims(img_chw, axis=0)
        
        padding_info = {
            'original_h': original_h,
            'original_w': original_w,
            'resized_h': new_h,
            'resized_w': new_w,
            'pad_top': pad_top,
            'pad_bottom': pad_bottom,
            'pad_left': pad_left,
            'pad_right': pad_right,
            'scale': scale
        }
        
        return img_batch, padding_info
    
    def _postprocess_onnx(self, output_tensor: np.ndarray, padding_info: dict = None) -> np.ndarray:
        """
        ONNX Runtime 결과 후처리
        
        Args:
            output_tensor: 모델 출력 (1, C, H, W, 0-1 범위)
            padding_info: 패딩 정보 (원본 크기 복원용)
            
        Returns:
            후처리된 이미지 (HWC, BGR 형식, 0-255 범위)
        """
        # 배치 차원 제거: (1, C, H, W) -> (C, H, W)
        output = output_tensor.squeeze(axis=0)
        
        # CHW -> HWC 변환
        output_hwc = output.transpose((1, 2, 0))
        
        # 0-1 범위 클리핑 및 0-255로 변환
        output_clipped = np.clip(output_hwc, 0.0, 1.0)
        output_uint8 = (output_clipped * 255.0).round().astype(np.uint8)
        
        # RGB -> BGR 변환 (OpenCV 저장용)
        output_bgr = cv2.cvtColor(output_uint8, cv2.COLOR_RGB2BGR)
        
        # 패딩 제거 및 원본 크기의 4배로 복원 (모델이 4배로 upscale했으므로)
        if padding_info:
            pad_top = padding_info['pad_top']
            pad_bottom = padding_info['pad_bottom']
            pad_left = padding_info['pad_left']
            pad_right = padding_info['pad_right']
            resized_h = padding_info['resized_h']
            resized_w = padding_info['resized_w']
            original_h = padding_info['original_h']
            original_w = padding_info['original_w']
            
            # 모델이 4배로 upscale했으므로 패딩과 리사이즈된 크기도 4배로 스케일링
            scale_factor = 4  # ONNX 모델의 upscale 배율
            pad_top_scaled = pad_top * scale_factor
            pad_bottom_scaled = pad_bottom * scale_factor
            pad_left_scaled = pad_left * scale_factor
            pad_right_scaled = pad_right * scale_factor
            resized_h_scaled = resized_h * scale_factor
            resized_w_scaled = resized_w * scale_factor
            
            # 패딩 제거
            if pad_top_scaled > 0 or pad_bottom_scaled > 0 or pad_left_scaled > 0 or pad_right_scaled > 0:
                output_bgr = output_bgr[pad_top_scaled:pad_top_scaled+resized_h_scaled, pad_left_scaled:pad_left_scaled+resized_w_scaled]
            
            # 원본 크기의 4배로 리사이즈 (모델이 4배로 upscale했으므로)
            target_h = original_h * scale_factor
            target_w = original_w * scale_factor
            output_bgr = cv2.resize(output_bgr, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        
        return output_bgr
    
    def _load_model_onnx(self, model_path: str):
        """
        ONNX Runtime 모델을 로드합니다.
        
        Args:
            model_path: ONNX 모델 파일 경로
            
        Returns:
            (ONNX Runtime InferenceSession 인스턴스, 입력 크기 정보)
        """
        # #region agent log
        import json
        import time
        from pathlib import Path
        log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"enhancement.py:130","message":"_load_model_onnx entry","data":{"model_path":model_path,"has_onnx_runtime":HAS_ONNX_RUNTIME},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        if not HAS_ONNX_RUNTIME:
            raise ImportError("ONNX Runtime not available")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX 모델 파일을 찾을 수 없습니다: {model_path}")
        
        # DirectML provider 우선, 실패 시 CPU fallback
        providers = [
            ('DmlExecutionProvider', {'device_id': 0}),
            'CPUExecutionProvider'
        ]
        
        # #region agent log
        try:
            available_providers = ort.get_available_providers()
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"enhancement.py:148","message":"Creating InferenceSession","data":{"available_providers":available_providers,"requested_providers":["DmlExecutionProvider","CPUExecutionProvider"]},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        try:
            session = ort.InferenceSession(model_path, providers=providers)
            actual_providers = session.get_providers()
            provider_name = actual_providers[0] if actual_providers else "Unknown"
            
            # 입력 크기 정보 추출
            input_shape = session.get_inputs()[0].shape
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"enhancement.py:157","message":"InferenceSession created","data":{"actual_providers":actual_providers,"provider_name":provider_name,"input_shape":input_shape},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            
            logger.info(f"ONNX Runtime 모델 로드 완료: {model_path}")
            logger.info(f"사용 중인 Provider: {provider_name}")
            logger.info(f"모델 입력 크기: {input_shape}")
            
            return session, input_shape
        except Exception as e:
            logger.error(f"ONNX Runtime 모델 로드 실패: {e}")
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"E","location":"enhancement.py:163","message":"InferenceSession creation failed","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            raise
    
    def __init__(self, model_path: str = None):
        """
        향상기 초기화
        
        Args:
            model_path: 모델 가중치 경로 (기본값: config.MODEL_PATH)
        """
        # #region agent log
        import json
        import time
        from pathlib import Path
        log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
        init_start = time.time()
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:30","message":"ImageEnhancer.__init__ entry","data":{},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        global _shared_upscaler, _upscaler_type, _onnx_input_shape
        
        # 싱글톤 패턴: 모델이 이미 로드되어 있으면 재사용
        with _upscaler_lock:
            if _shared_upscaler is None:
                # 백엔드 감지
                backend = self._detect_available_backend()
                logger.info(f"감지된 백엔드: {backend}")
                
                # 디바이스 선택 로직
                use_onnx = False
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"enhancement.py:193","message":"Backend selection start","data":{"backend":backend},"timestamp":int(time.time()*1000)})+"\n")
                except: pass
                # #endregion
                if backend == "directml":
                    # DirectML 사용 가능: ONNX Runtime 시도
                    onnx_model_path = config.MODEL_PATH_ONNX if hasattr(config, 'MODEL_PATH_ONNX') else None
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"enhancement.py:197","message":"DirectML backend - checking ONNX model","data":{"onnx_model_path":onnx_model_path,"path_exists":os.path.exists(onnx_model_path) if onnx_model_path else False},"timestamp":int(time.time()*1000)})+"\n")
                    except: pass
                    # #endregion
                    if onnx_model_path:
                        if os.path.exists(onnx_model_path):
                            try:
                                session_result = self._load_model_onnx(onnx_model_path)
                                if isinstance(session_result, tuple):
                                    _shared_upscaler, input_shape = session_result
                                else:
                                    _shared_upscaler = session_result
                                    input_shape = None
                                _upscaler_type = "onnx"
                                _onnx_input_shape = input_shape  # 입력 크기 정보 저장
                                use_onnx = True
                                logger.info("ONNX Runtime (DirectML) 모델 로드 성공")
                                # #region agent log
                                try:
                                    with open(log_path, "a", encoding="utf-8") as f:
                                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"enhancement.py:202","message":"ONNX model loaded successfully","data":{"upscaler_type":"onnx","input_shape":str(input_shape) if input_shape else None},"timestamp":int(time.time()*1000)})+"\n")
                                except: pass
                                # #endregion
                            except Exception as e:
                                logger.warning(f"ONNX Runtime 로드 실패, PyTorch로 fallback: {e}")
                                use_onnx = False
                                # #region agent log
                                try:
                                    with open(log_path, "a", encoding="utf-8") as f:
                                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"enhancement.py:207","message":"ONNX load failed - fallback to PyTorch","data":{"error":str(e)},"timestamp":int(time.time()*1000)})+"\n")
                                except: pass
                                # #endregion
                        else:
                            logger.warning(f"ONNX 모델 파일을 찾을 수 없습니다: {onnx_model_path}. PyTorch로 fallback합니다.")
                            use_onnx = False
                            # #region agent log
                            try:
                                with open(log_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"enhancement.py:211","message":"ONNX model file not found","data":{"onnx_model_path":onnx_model_path},"timestamp":int(time.time()*1000)})+"\n")
                            except: pass
                            # #endregion
                    else:
                        logger.debug("MODEL_PATH_ONNX가 설정되지 않았습니다. PyTorch를 사용합니다.")
                        use_onnx = False
                        # #region agent log
                        try:
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"D","location":"enhancement.py:216","message":"MODEL_PATH_ONNX not configured","data":{},"timestamp":int(time.time()*1000)})+"\n")
                        except: pass
                        # #endregion
                
                # ONNX 사용하지 않는 경우 PyTorch 방식 사용
                if not use_onnx:
                    # #region agent log
                    try:
                        with open(log_path, "a", encoding="utf-8") as f:
                            f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"enhancement.py:214","message":"Using PyTorch backend","data":{"backend":backend,"has_realesrgan":HAS_REALESRGAN},"timestamp":int(time.time()*1000)})+"\n")
                    except: pass
                    # #endregion
                    if model_path is None:
                        model_path = config.MODEL_PATH
                    
                    if HAS_REALESRGAN:
                        try:
                            _shared_upscaler = self._load_model_pytorch(model_path)
                            _upscaler_type = "pytorch"
                            logger.info(f"PyTorch 모델 로드 성공 (백엔드: {backend})")
                            # #region agent log
                            try:
                                with open(log_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"enhancement.py:222","message":"PyTorch model loaded","data":{"upscaler_type":"pytorch","backend":backend},"timestamp":int(time.time()*1000)})+"\n")
                            except: pass
                            # #endregion
                        except Exception as e:
                            logger.error(f"PyTorch 모델 로드 실패: {e}")
                            _shared_upscaler = None
                            _upscaler_type = None
                            # #region agent log
                            try:
                                with open(log_path, "a", encoding="utf-8") as f:
                                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"F","location":"enhancement.py:227","message":"PyTorch model load failed","data":{"error":str(e)},"timestamp":int(time.time()*1000)})+"\n")
                            except: pass
                            # #endregion
                    else:
                        logger.warning("RealESRGAN 라이브러리를 사용할 수 없습니다. 이미지 향상 기능이 비활성화됩니다.")
                        _shared_upscaler = None
                        _upscaler_type = None
                
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:54","message":"shared upscaler created","data":{"model_path":model_path,"upscaler_type":_upscaler_type,"backend":backend},"timestamp":int(time.time()*1000)})+"\n")
                except: pass
                # #endregion
        
        # 모든 인스턴스가 동일한 upscaler를 공유
        self.upscaler = _shared_upscaler
        self.upscaler_type = _upscaler_type
        self.onnx_input_shape = _onnx_input_shape
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"G","location":"enhancement.py:228","message":"ImageEnhancer initialized","data":{"upscaler_type":self.upscaler_type,"has_upscaler":self.upscaler is not None,"onnx_input_shape":str(self.onnx_input_shape) if self.onnx_input_shape else None},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # #region agent log
        init_duration = time.time() - init_start
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:62","message":"ImageEnhancer.__init__ exit","data":{"duration_seconds":init_duration,"has_upscaler":self.upscaler is not None,"is_shared":_shared_upscaler is not None},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
    
    def upscale_onnx(self, img: np.ndarray) -> np.ndarray:
        """
        ONNX Runtime을 사용하여 이미지를 upscale합니다.
        
        Args:
            img: 입력 이미지 (BGR 형식)
            
        Returns:
            향상된 이미지 (SR_SCALE배 확대)
        """
        # #region agent log
        import json
        import time
        from pathlib import Path
        log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
        upscale_start = time.time()
        h, w = img.shape[:2]
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"enhancement.py:486","message":"upscale_onnx entry","data":{"input_size_h":h,"input_size_w":w,"onnx_input_shape":str(self.onnx_input_shape) if self.onnx_input_shape else None},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        if self.upscaler is None:
            raise ImportError("ONNX Runtime session not initialized")
        
        # 모델 입력 크기 확인
        target_h = None
        target_w = None
        if self.onnx_input_shape:
            # 입력 shape: [batch, channels, height, width]
            if len(self.onnx_input_shape) >= 4:
                target_h = self.onnx_input_shape[2] if self.onnx_input_shape[2] is not None else 128
                target_w = self.onnx_input_shape[3] if self.onnx_input_shape[3] is not None else 128
            elif len(self.onnx_input_shape) >= 2:
                # 동적 크기인 경우 기본값 사용
                target_h = 128
                target_w = 128
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"enhancement.py:510","message":"Preprocessing start","data":{"target_h":target_h,"target_w":target_w},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # 전처리 (패딩 포함)
        input_tensor, padding_info = self._preprocess_onnx(img, target_h, target_w)
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"enhancement.py:515","message":"Preprocessing done","data":{"input_tensor_shape":list(input_tensor.shape),"padding_info":padding_info},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # 추론 실행 (동시성 제어: DirectML은 동시 실행에 제한이 있음)
        input_name = self.upscaler.get_inputs()[0].name
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"enhancement.py:520","message":"Inference start","data":{"input_name":input_name},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # DirectML은 동시 실행에 제한이 있으므로 락 사용
        global _onnx_inference_lock
        with _onnx_inference_lock:
            output_tensor = self.upscaler.run(None, {input_name: input_tensor})[0]
        
        # #region agent log
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"enhancement.py:525","message":"Inference done","data":{"output_tensor_shape":list(output_tensor.shape)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # 후처리 (패딩 제거 및 원본 크기 복원)
        result_img = self._postprocess_onnx(output_tensor, padding_info)
        
        # #region agent log
        try:
            result_h, result_w = result_img.shape[:2]
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"enhancement.py:532","message":"Postprocessing done","data":{"result_size_h":result_h,"result_size_w":result_w},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        # ONNX 모델은 x4 스케일로 학습되었으므로,
        # SR_SCALE이 4인 경우 모델 출력을 그대로 사용 (resize 불필요)
        # SR_SCALE이 4가 아닌 경우에만 resize 수행
        expected_h = h * config.SR_SCALE
        expected_w = w * config.SR_SCALE
        result_h, result_w = result_img.shape[:2]
        
        if result_h != expected_h or result_w != expected_w:
            # resize로 원하는 크기로 조정 (SR_SCALE이 4가 아닌 경우에만 발생)
            result_img = cv2.resize(result_img, (expected_w, expected_h), interpolation=cv2.INTER_LINEAR)
        
        # #region agent log
        upscale_duration = time.time() - upscale_start
        final_h, final_w = result_img.shape[:2]
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"H","location":"enhancement.py:545","message":"upscale_onnx exit","data":{"duration_seconds":upscale_duration,"final_size_h":final_h,"final_size_w":final_w},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        return result_img
    
    def _load_model_pytorch(self, model_path: str):
        """
        PyTorch 기반 Real-ESRGAN 모델을 로드합니다.
        
        Args:
            model_path: 모델 가중치 경로
        
        Returns:
            RealESRGANer 인스턴스
        """
        # #region agent log
        import json
        import time
        from pathlib import Path
        log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
        load_start = time.time()
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:44","message":"_load_model entry","data":{"model_path":model_path},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
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
            scale=4
        )
        
        # 디바이스 설정
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # RealESRGANer 초기화
        # scale=4: x4plus 모델 고유 배율. outscale은 enhance()에서 SR_SCALE로 적용.
        result = RealESRGANer(
            scale=4,
            model_path=model_path,
            model=model,
            tile=0,
            pre_pad=0,
            half=(device.type == 'cuda'),
            device=device
        )
        
        # #region agent log
        load_duration = time.time() - load_start
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"A","location":"enhancement.py:88","message":"_load_model exit","data":{"duration_seconds":load_duration,"device":str(device)},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        return result
    
    def upscale(self, img: np.ndarray) -> np.ndarray:
        """
        이미지를 초해상도로 향상시킵니다.

        Args:
            img: 입력 이미지 (BGR 형식)

        Returns:
            향상된 이미지 (SR_SCALE배 확대)
        """
        # #region agent log
        import json
        import time
        from pathlib import Path
        log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
        upscale_start = time.time()
        h, w = img.shape[:2]
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:90","message":"upscale entry","data":{"input_size_h":h,"input_size_w":w,"pixels":h*w},"timestamp":int(time.time()*1000)})+"\n")
        except: pass
        # #endregion
        
        try:
            if self.upscaler is None:
                raise ImportError("Upscaler not initialized")
            
            # #region agent log
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:688","message":"Checking upscaler type","data":{"upscaler_type":self.upscaler_type,"has_upscaler":self.upscaler is not None},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            
            # upscaler 타입에 따라 적절한 메서드 호출
            if self.upscaler_type == "onnx":
                # ONNX Runtime 방식
                logger.info(f"Upscale 진행 중: ONNX Runtime (DirectML) ({h}x{w} -> {h * config.SR_SCALE}x{w * config.SR_SCALE})")
                # #region agent log
                try:
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:692","message":"Calling upscale_onnx","data":{},"timestamp":int(time.time()*1000)})+"\n")
                except: pass
                # #endregion
                output = self.upscale_onnx(img)
            elif self.upscaler_type == "pytorch":
                # PyTorch 방식
                logger.info(f"Upscale 진행 중: PyTorch Real-ESRGAN ({h}x{w} -> {h * config.SR_SCALE}x{w * config.SR_SCALE})")
                output, _ = self.upscaler.enhance(img, outscale=config.SR_SCALE)
            else:
                raise ImportError(f"Unknown upscaler type: {self.upscaler_type}")
            
            # #region agent log
            upscale_duration = time.time() - upscale_start
            output_h, output_w = output.shape[:2]
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:106","message":"upscale exit","data":{"duration_seconds":upscale_duration,"output_size_h":output_h,"output_size_w":output_w,"upscaler_type":self.upscaler_type},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            
            logger.info(f"Upscale 완료: {output.shape[0]}x{output.shape[1]} (백엔드: {self.upscaler_type})")
            return output
        except Exception as e:
            # #region agent log
            upscale_duration = time.time() - upscale_start
            import traceback
            try:
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"sessionId":"debug-session","runId":"run1","hypothesisId":"B","location":"enhancement.py:109","message":"upscale fallback","data":{"duration_seconds":upscale_duration,"error":str(e),"error_type":type(e).__name__,"upscaler_type":self.upscaler_type,"traceback":traceback.format_exc()},"timestamp":int(time.time()*1000)})+"\n")
            except: pass
            # #endregion
            logger.warning(f"Upscale 실패, cv2.resize fallback: {e}")
            logger.error(f"에러 상세: {traceback.format_exc()}")
            return cv2.resize(img, (w * config.SR_SCALE, h * config.SR_SCALE))

def enhancement_node(state: GraphState) -> Dict[str, Any]:
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

