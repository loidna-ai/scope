"""
?μ긽 ?몃뱶
Real-ESRGAN???ъ슜?섏뿬 ?대?吏瑜?2諛?珥덊빐?곷룄濡??μ긽?쒗궢?덈떎.
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
except ImportError as e:
    HAS_ONNX_RUNTIME = False
    ort = None
    logger.debug("ONNX Runtime not available. ONNX-based acceleration will be disabled.")
except Exception as e:
    HAS_ONNX_RUNTIME = False
    ort = None
    logger.debug(f"ONNX Runtime initialization failed: {e}")

# from src.state import GraphState  # ?꾩옱 ?ъ슜?섏? ?딆쓬 (enhancement_node ?⑥닔 誘몄궗??
import config
import threading

# ?깃????⑦꽩: 紐⑤뜽????踰덈쭔 濡쒕뱶?섍퀬 ?ъ궗??
_shared_upscaler = None
_upscaler_type = None  # "onnx" ?먮뒗 "pytorch"
_onnx_input_shape = None  # ONNX 紐⑤뜽 ?낅젰 ?ш린 ?뺣낫
_upscaler_lock = threading.Lock()
_onnx_inference_lock = threading.Lock()  # ONNX 異붾줎 ?숈떆???쒖뼱

class ImageEnhancer:
    """Real-ESRGAN 湲곕컲 ?대?吏 ?μ긽 ?대옒??(?깃????⑦꽩?쇰줈 紐⑤뜽 怨듭쑀)
    
    ?섏씠釉뚮━???묎렐 諛⑹떇:
    - CUDA ?ъ슜 媛?? PyTorch 諛⑹떇 ?ъ슜
    - DirectML ?ъ슜 媛?? ONNX Runtime 諛⑹떇 ?ъ슜
    - CPU留??ъ슜 媛?? PyTorch 諛⑹떇 ?ъ슜
    """
    
    @staticmethod
    def _detect_available_backend():
        """
        ?ъ슜 媛?ν븳 諛깆뿏?쒕? 媛먯??⑸땲??
        
        Returns:
            str: "cuda", "directml", ?먮뒗 "cpu"
        """
        # CUDA ?곗꽑?쒖쐞 1
        if torch.cuda.is_available():
            return "cuda"
        
        # DirectML ?곗꽑?쒖쐞 2 (AMD GPU)
        if HAS_ONNX_RUNTIME:
            try:
                # DirectML provider ?ъ슜 媛???щ? ?뺤씤
                available_providers = ort.get_available_providers()
                if 'DmlExecutionProvider' in available_providers:
                    return "directml"
            except Exception as e:
                logger.debug(f"DirectML 媛먯? ?ㅽ뙣: {e}")
        
        # CPU fallback
        return "cpu"
    
    def _preprocess_onnx(self, img: np.ndarray, target_h: int = None, target_w: int = None) -> tuple:
        """
        ONNX Runtime???대?吏 ?꾩쿂由?
        
        Args:
            img: ?낅젰 ?대?吏 (BGR ?뺤떇, HWC)
            target_h: 紐⑺몴 ?믪씠 (None?대㈃ 紐⑤뜽 ?낅젰 ?ш린 ?ъ슜)
            target_w: 紐⑺몴 ?덈퉬 (None?대㈃ 紐⑤뜽 ?낅젰 ?ш린 ?ъ슜)
            
        Returns:
            (?꾩쿂由щ맂 ?대?吏 ?먯꽌, ?먮낯 ?ш린 ?뺣낫, ?⑤뵫 ?뺣낫)
        """
        original_h, original_w = img.shape[:2]
        
        # 紐⑤뜽???붽뎄?섎뒗 ?ш린濡?由ъ궗?댁쫰 (怨좎젙 ?ш린 紐⑤뜽 ???
        if target_h is None or target_w is None:
            # 湲곕낯媛? 紐⑤뜽???붽뎄?섎뒗 ?ш린 (128x128)
            target_h = 128
            target_w = 128
        
        # 由ъ궗?댁쫰 (鍮꾩쑉 ?좎??섎㈃???⑤뵫 異붽?)
        scale = min(target_h / original_h, target_w / original_w)
        new_h = int(original_h * scale)
        new_w = int(original_w * scale)
        
        img_resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # ?⑤뵫 異붽? (以묒븰 ?뺣젹)
        pad_top = (target_h - new_h) // 2
        pad_bottom = target_h - new_h - pad_top
        pad_left = (target_w - new_w) // 2
        pad_right = target_w - new_w - pad_left
        
        img_padded = cv2.copyMakeBorder(
            img_resized, pad_top, pad_bottom, pad_left, pad_right,
            cv2.BORDER_REPLICATE
        )
        
        # BGR -> RGB 蹂??
        img_rgb = cv2.cvtColor(img_padded, cv2.COLOR_BGR2RGB)
        
        # 0-255 -> 0-1 ?뺢퇋??
        img_normalized = img_rgb.astype(np.float32) / 255.0
        
        # HWC -> CHW 蹂??
        img_chw = img_normalized.transpose((2, 0, 1))
        
        # 諛곗튂 李⑥썝 異붽?: (C, H, W) -> (1, C, H, W)
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
        ONNX Runtime 寃곌낵 ?꾩쿂由?
        
        Args:
            output_tensor: 紐⑤뜽 異쒕젰 (1, C, H, W, 0-1 踰붿쐞)
            padding_info: ?⑤뵫 ?뺣낫 (?먮낯 ?ш린 蹂듭썝??
            
        Returns:
            ?꾩쿂由щ맂 ?대?吏 (HWC, BGR ?뺤떇, 0-255 踰붿쐞)
        """
        # 諛곗튂 李⑥썝 ?쒓굅: (1, C, H, W) -> (C, H, W)
        output = output_tensor.squeeze(axis=0)
        
        # CHW -> HWC 蹂??
        output_hwc = output.transpose((1, 2, 0))
        
        # 0-1 踰붿쐞 ?대━??諛?0-255濡?蹂??
        output_clipped = np.clip(output_hwc, 0.0, 1.0)
        output_uint8 = (output_clipped * 255.0).round().astype(np.uint8)
        
        # RGB -> BGR 蹂??(OpenCV ??μ슜)
        output_bgr = cv2.cvtColor(output_uint8, cv2.COLOR_RGB2BGR)
        
        # ?⑤뵫 ?쒓굅 諛??먮낯 ?ш린??4諛곕줈 蹂듭썝 (紐⑤뜽??4諛곕줈 upscale?덉쑝誘濡?
        if padding_info:
            pad_top = padding_info['pad_top']
            pad_bottom = padding_info['pad_bottom']
            pad_left = padding_info['pad_left']
            pad_right = padding_info['pad_right']
            resized_h = padding_info['resized_h']
            resized_w = padding_info['resized_w']
            original_h = padding_info['original_h']
            original_w = padding_info['original_w']
            
            # 紐⑤뜽??4諛곕줈 upscale?덉쑝誘濡??⑤뵫怨?由ъ궗?댁쫰???ш린??4諛곕줈 ?ㅼ??쇰쭅
            scale_factor = config.SR_SCALE  # ONNX 紐⑤뜽??upscale 諛곗쑉
            pad_top_scaled = pad_top * scale_factor
            pad_bottom_scaled = pad_bottom * scale_factor
            pad_left_scaled = pad_left * scale_factor
            pad_right_scaled = pad_right * scale_factor
            resized_h_scaled = resized_h * scale_factor
            resized_w_scaled = resized_w * scale_factor
            
            # ?⑤뵫 ?쒓굅
            if pad_top_scaled > 0 or pad_bottom_scaled > 0 or pad_left_scaled > 0 or pad_right_scaled > 0:
                output_bgr = output_bgr[pad_top_scaled:pad_top_scaled+resized_h_scaled, pad_left_scaled:pad_left_scaled+resized_w_scaled]
            
            # ?먮낯 ?ш린??4諛곕줈 由ъ궗?댁쫰 (紐⑤뜽??4諛곕줈 upscale?덉쑝誘濡?
            target_h = original_h * scale_factor
            target_w = original_w * scale_factor
            output_bgr = cv2.resize(output_bgr, (target_w, target_h), interpolation=cv2.INTER_LINEAR)
        
        return output_bgr
    
    def _load_model_onnx(self, model_path: str):
        """
        ONNX Runtime 紐⑤뜽??濡쒕뱶?⑸땲??
        
        Args:
            model_path: ONNX 紐⑤뜽 ?뚯씪 寃쎈줈
            
        Returns:
            (ONNX Runtime InferenceSession ?몄뒪?댁뒪, ?낅젰 ?ш린 ?뺣낫)
        """
        if not HAS_ONNX_RUNTIME:
            raise ImportError("ONNX Runtime not available")
        
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX 紐⑤뜽 ?뚯씪??李얠쓣 ???놁뒿?덈떎: {model_path}")
        
        # DirectML provider ?곗꽑, ?ㅽ뙣 ??CPU fallback
        providers = [
            ('DmlExecutionProvider', {'device_id': 0}),
            'CPUExecutionProvider'
        ]
        
        try:
            session = ort.InferenceSession(model_path, providers=providers)
            actual_providers = session.get_providers()
            provider_name = actual_providers[0] if actual_providers else "Unknown"
            
            # ?낅젰 ?ш린 ?뺣낫 異붿텧
            input_shape = session.get_inputs()[0].shape
            
            logger.info(f"ONNX Runtime 紐⑤뜽 濡쒕뱶 ?꾨즺: {model_path}")
            logger.info(f"?ъ슜 以묒씤 Provider: {provider_name}")
            logger.info(f"紐⑤뜽 ?낅젰 ?ш린: {input_shape}")
            
            return session, input_shape
        except Exception as e:
            logger.error(f"ONNX Runtime 紐⑤뜽 濡쒕뱶 ?ㅽ뙣: {e}")
            raise
    
    def __init__(self, model_path: str = None):
        """
        ?μ긽湲?珥덇린??
        
        Args:
            model_path: 紐⑤뜽 媛以묒튂 寃쎈줈 (湲곕낯媛? config.MODEL_PATH)
        """
        global _shared_upscaler, _upscaler_type, _onnx_input_shape
        
        # ?깃????⑦꽩: 紐⑤뜽???대? 濡쒕뱶?섏뼱 ?덉쑝硫??ъ궗??
        with _upscaler_lock:
            if _shared_upscaler is None:
                # 諛깆뿏??媛먯?
                backend = self._detect_available_backend()
                logger.info(f"媛먯???諛깆뿏?? {backend}")
                
                # ?붾컮?댁뒪 ?좏깮 濡쒖쭅
                use_onnx = False
                if backend == "directml":
                    # DirectML ?ъ슜 媛?? ONNX Runtime ?쒕룄
                    onnx_model_path = config.MODEL_PATH_ONNX if hasattr(config, 'MODEL_PATH_ONNX') else None
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
                                _onnx_input_shape = input_shape  # ?낅젰 ?ш린 ?뺣낫 ???
                                use_onnx = True
                                logger.info("ONNX Runtime (DirectML) 紐⑤뜽 濡쒕뱶 ?깃났")
                            except Exception as e:
                                logger.warning(f"ONNX Runtime 濡쒕뱶 ?ㅽ뙣, PyTorch濡?fallback: {e}")
                                use_onnx = False
                        else:
                            logger.warning(f"ONNX 紐⑤뜽 ?뚯씪??李얠쓣 ???놁뒿?덈떎: {onnx_model_path}. PyTorch濡?fallback?⑸땲??")
                            use_onnx = False
                    else:
                        logger.debug("MODEL_PATH_ONNX媛 ?ㅼ젙?섏? ?딆븯?듬땲?? PyTorch瑜??ъ슜?⑸땲??")
                        use_onnx = False
                
                # ONNX ?ъ슜?섏? ?딅뒗 寃쎌슦 PyTorch 諛⑹떇 ?ъ슜
                if not use_onnx:
                    if model_path is None:
                        model_path = config.MODEL_PATH
                    
                    if HAS_REALESRGAN:
                        try:
                            _shared_upscaler = self._load_model_pytorch(model_path)
                            _upscaler_type = "pytorch"
                            logger.info(f"PyTorch 紐⑤뜽 濡쒕뱶 ?깃났 (諛깆뿏?? {backend})")
                        except Exception as e:
                            logger.error(f"PyTorch 紐⑤뜽 濡쒕뱶 ?ㅽ뙣: {e}")
                            _shared_upscaler = None
                            _upscaler_type = None
                    else:
                        logger.warning("RealESRGAN ?쇱씠釉뚮윭由щ? ?ъ슜?????놁뒿?덈떎. ?대?吏 ?μ긽 湲곕뒫??鍮꾪솢?깊솕?⑸땲??")
                        _shared_upscaler = None
                        _upscaler_type = None
        
        # 紐⑤뱺 ?몄뒪?댁뒪媛 ?숈씪??upscaler瑜?怨듭쑀
        self.upscaler = _shared_upscaler
        self.upscaler_type = _upscaler_type
        self.onnx_input_shape = _onnx_input_shape
    
    def upscale_onnx(self, img: np.ndarray) -> np.ndarray:
        """
        ONNX Runtime???ъ슜?섏뿬 ?대?吏瑜?upscale?⑸땲??
        
        Args:
            img: ?낅젰 ?대?吏 (BGR ?뺤떇)
            
        Returns:
            ?μ긽???대?吏 (SR_SCALE諛??뺣?)
        """
        h, w = img.shape[:2]
        if self.upscaler is None:
            raise ImportError("ONNX Runtime session not initialized")
        
        # 紐⑤뜽 ?낅젰 ?ш린 ?뺤씤
        target_h = None
        target_w = None
        if self.onnx_input_shape:
            # ?낅젰 shape: [batch, channels, height, width]
            if len(self.onnx_input_shape) >= 4:
                target_h = self.onnx_input_shape[2] if self.onnx_input_shape[2] is not None else 128
                target_w = self.onnx_input_shape[3] if self.onnx_input_shape[3] is not None else 128
            elif len(self.onnx_input_shape) >= 2:
                # ?숈쟻 ?ш린??寃쎌슦 湲곕낯媛??ъ슜
                target_h = 128
                target_w = 128
        
        # ?꾩쿂由?(?⑤뵫 ?ы븿)
        input_tensor, padding_info = self._preprocess_onnx(img, target_h, target_w)
        
        # 異붾줎 ?ㅽ뻾 (?숈떆???쒖뼱: DirectML? ?숈떆 ?ㅽ뻾???쒗븳???덉쓬)
        input_name = self.upscaler.get_inputs()[0].name
        
        # DirectML? ?숈떆 ?ㅽ뻾???쒗븳???덉쑝誘濡????ъ슜
        global _onnx_inference_lock
        with _onnx_inference_lock:
            output_tensor = self.upscaler.run(None, {input_name: input_tensor})[0]
        
        # ?꾩쿂由?(?⑤뵫 ?쒓굅 諛??먮낯 ?ш린 蹂듭썝)
        result_img = self._postprocess_onnx(output_tensor, padding_info)
        
        # ONNX 紐⑤뜽? x4 ?ㅼ??쇰줈 ?숈뒿?섏뿀?쇰?濡?
        # SR_SCALE??4??寃쎌슦 紐⑤뜽 異쒕젰??洹몃?濡??ъ슜 (resize 遺덊븘??
        # SR_SCALE??4媛 ?꾨땶 寃쎌슦?먮쭔 resize ?섑뻾
        expected_h = h * config.SR_SCALE
        expected_w = w * config.SR_SCALE
        result_h, result_w = result_img.shape[:2]
        
        if result_h != expected_h or result_w != expected_w:
            # resize濡??먰븯???ш린濡?議곗젙 (SR_SCALE??4媛 ?꾨땶 寃쎌슦?먮쭔 諛쒖깮)
            result_img = cv2.resize(result_img, (expected_w, expected_h), interpolation=cv2.INTER_LINEAR)
        
        return result_img
    
    def _load_model_pytorch(self, model_path: str):
        """
        PyTorch 湲곕컲 Real-ESRGAN 紐⑤뜽??濡쒕뱶?⑸땲??
        
        Args:
            model_path: 紐⑤뜽 媛以묒튂 寃쎈줈
        
        Returns:
            RealESRGANer ?몄뒪?댁뒪
        """
        # 紐⑤뜽 ?붾젆?좊━ ?앹꽦
        model_dir = os.path.dirname(model_path)
        if model_dir and not os.path.exists(model_dir):
            os.makedirs(model_dir, exist_ok=True)
        
        # 紐⑤뜽???놁쑝硫??ㅼ슫濡쒕뱶
        if not os.path.exists(model_path):
            logger.info(f"紐⑤뜽 ?ㅼ슫濡쒕뱶 以? {model_path}")
            url = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth'
            torch.hub.download_url_to_file(url, model_path)
        
        # 紐⑤뜽 ?꾪궎?띿쿂 ?뺤쓽
        model = RRDBNet(
            num_in_ch=3, 
            num_out_ch=3, 
            num_feat=64, 
            num_block=23, 
            num_grow_ch=32, 
            scale=config.SR_SCALE)
        
        # ?붾컮?댁뒪 ?ㅼ젙
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # RealESRGANer 珥덇린??
        # scale=config.SR_SCALE: x4plus 紐⑤뜽 怨좎쑀 諛곗쑉. outscale? enhance()?먯꽌 SR_SCALE濡??곸슜.
        result = RealESRGANer(
            scale=config.SR_SCALE,
            model_path=model_path,
            model=model,
            tile=0,
            pre_pad=0,
            half=(device.type == 'cuda'),
            device=device
        )
        
        return result
    
    def upscale(self, img: np.ndarray) -> np.ndarray:
        """
        ?대?吏瑜?珥덊빐?곷룄濡??μ긽?쒗궢?덈떎.

        Args:
            img: ?낅젰 ?대?吏 (BGR ?뺤떇)

        Returns:
            ?μ긽???대?吏 (SR_SCALE諛??뺣?)
        """
        h, w = img.shape[:2]
        try:
            if self.upscaler is None:
                raise ImportError("Upscaler not initialized")
            
            # upscaler ??낆뿉 ?곕씪 ?곸젅??硫붿꽌???몄텧
            if self.upscaler_type == "onnx":
                # ONNX Runtime 諛⑹떇
                logger.info(f"Upscale 吏꾪뻾 以? ONNX Runtime (DirectML) ({h}x{w} -> {h * config.SR_SCALE}x{w * config.SR_SCALE})")
                output = self.upscale_onnx(img)
            elif self.upscaler_type == "pytorch":
                # PyTorch 諛⑹떇
                logger.info(f"Upscale 吏꾪뻾 以? PyTorch Real-ESRGAN ({h}x{w} -> {h * config.SR_SCALE}x{w * config.SR_SCALE})")
                output, _ = self.upscaler.enhance(img, outscale=config.SR_SCALE)
            else:
                raise ImportError(f"Unknown upscaler type: {self.upscaler_type}")
            
            logger.info(f"Upscale ?꾨즺: {output.shape[0]}x{output.shape[1]} (諛깆뿏?? {self.upscaler_type})")
            return output
        except Exception as e:
            import traceback
            logger.warning(f"Upscale ?ㅽ뙣, cv2.resize fallback: {e}")
            logger.error(f"?먮윭 ?곸꽭: {traceback.format_exc()}")
            return cv2.resize(img, (w * config.SR_SCALE, h * config.SR_SCALE))

# def enhancement_node  # 현재 미사용 함수(state: GraphState) -> Dict[str, Any]:
#     """
#     ?μ긽 ?몃뱶
    
#     Args:
#         state: 洹몃옒???곹깭
    
#     Returns:
#         ?낅뜲?댄듃???곹깭 ?꾨뱶 (Partial State)
#     """
#     if state.get("cropped_image") is None:
#         return {
#             "errors": ["?μ긽 ?ㅽ뙣: ?щ∼???대?吏媛 ?놁뒿?덈떎."]
#         }
    
#     try:
#         enhancer = ImageEnhancer()
#         input_img = state["cropped_image"]
        
#         # ?낅젰 ?ш린 ???
#         input_h, input_w = input_img.shape[:2]
        
#         # ?μ긽 ?섑뻾
#         enhanced_img = enhancer.upscale(input_img)
        
#         # ?ш린 寃利?
#         output_h, output_w = enhanced_img.shape[:2]
#         expected_h = input_h * config.SR_SCALE
#         expected_w = input_w * config.SR_SCALE
        
#         # 寃利??ㅽ뙣 ??寃쎄퀬 濡쒓렇
#         if abs(output_h - expected_h) > 1 or abs(output_w - expected_w) > 1:
#             logger.warning(
#                 f"?ш린 寃利??ㅽ뙣: ?덉긽 ({expected_h}x{expected_w}), "
#                 f"?ㅼ젣 ({output_h}x{output_w})"
#             )
        
#         return {
#             "enhanced_image": enhanced_img
#         }
#     except Exception as e:
#         error_msg = f"?μ긽 ?ㅽ뙣: {str(e)}"
#         return {
#             "errors": [error_msg]
#         }



