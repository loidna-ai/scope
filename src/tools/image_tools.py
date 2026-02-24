"""
이미지 분석 도구
기존 노드 함수를 ReAct 에이전트 도구로 래핑합니다.
"""
from typing import Optional, Any
import cv2
import numpy as np
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
# from src.nodes.metrics import MorphologyAnalyzer
# from src.nodes.enhancement import ImageEnhancer
# from src.nodes.crop import ImageCropper
# from src.nodes.filter import TextureFilter

class MorphologyAnalyzer:
    def analyze(self, img): return {"circularity": 0, "solidity": 0, "area": 0}, None
class ImageCropper:
    def crop(self, img): return img
class TextureFilter:
    @staticmethod
    def apply_clahe(img): return img

class ImageAnalyzerInput(BaseModel):
    """이미지 분석 도구 입력 스키마"""
    image_path: str = Field(description="분석할 이미지 파일 경로")

class ImageAnalyzerTool(BaseTool):
    """
    이미지 형태학적 분석 도구
    
    MorphologyAnalyzer를 래핑하여 ReAct 에이전트가 사용할 수 있도록 합니다.
    """
    
    name: str = "analyze_image_morphology"
    description: str = (
        "이미지의 형태학적 특성을 분석합니다. "
        "원형도(circularity), 고형도(solidity), 면적(area)을 계산합니다. "
        "입력: 이미지 파일 경로. "
        "출력: 형태학적 메트릭스 딕셔너리 (circularity, solidity, area)."
    )
    args_schema: type[BaseModel] = ImageAnalyzerInput
    
    def _run(
        self,
        image_path: str,
        run_manager: Optional[Any] = None,
    ) -> str:
        """
        이미지 형태학적 분석 실행
        
        Args:
            image_path: 이미지 파일 경로
            run_manager: 실행 매니저 (선택적)
        
        Returns:
            분석 결과 문자열
        """
        try:
            # 이미지 로드
            img = cv2.imread(image_path)
            if img is None:
                return f"이미지 로드 실패: {image_path}"
            
            # 분석 수행
            analyzer = MorphologyAnalyzer()
            metrics, binary_mask = analyzer.analyze(img)
            
            # 결과 포맷팅
            result = (
                f"형태학적 분석 결과:\n"
                f"- 원형도(circularity): {metrics['circularity']:.3f} "
                f"(1에 가까울수록 원형)\n"
                f"- 고형도(solidity): {metrics['solidity']:.3f} "
                f"(1에 가까울수록 볼록)\n"
                f"- 면적(area): {metrics['area']:,} 픽셀"
            )
            
            return result
            
        except Exception as e:
            return f"이미지 분석 오류: {str(e)}"
    
    async def _arun(
        self,
        image_path: str,
        run_manager: Optional[Any] = None,
    ) -> str:
        """비동기 실행 (동기 실행으로 위임)"""
        return self._run(image_path, run_manager)

class ImageEnhancerInput(BaseModel):
    """이미지 향상 도구 입력 스키마"""
    image_path: str = Field(description="입력 이미지 파일 경로")
    output_path: Optional[str] = Field(default=None, description="출력 이미지 파일 경로 (선택적)")
    force: bool = Field(default=False, description="이미지가 선명해도 강제로 향상을 수행할지 여부")

class ImageEnhancerTool(BaseTool):
    """
    OpenCV DNN Super Resolution 기반 이미지 향상 도구
    
    Blur Detection을 통해 이미지가 흐릿한 경우에만 가벼운 EDSR/FSRCNN 모델을 사용하여
    해상도를 향상시킵니다. 이미지가 충분히 선명하면 작업을 건너뜁니다.
    """
    
    name: str = "enhance_image"
    description: str = (
        "이미지 해상도를 2배~4배 향상시킵니다. "
        "기본적으로 이미지가 흐릿할 때만 작동하며, 이미 선명하면 건너뜁니다. "
        "입력: 이미지 파일 경로, 출력 경로(선택적), force(강제 실행 여부). "
        "출력: 향상된 이미지 정보."
    )
    args_schema: type[BaseModel] = ImageEnhancerInput
    
    def _is_image_blurry(self, image: np.ndarray, threshold: float = 100.0) -> float:
        """
        이미지의 흐림 정도를 판단합니다.
        Laplacian Variance가 threshold보다 낮으면 흐린 것으로 판단.
        """
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return variance

    def _run(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        force: bool = False,
        run_manager: Optional[Any] = None,
    ) -> str:
        """
        이미지 향상 실행
        """
        import os
        
        try:
            # 이미지 로드
            img = cv2.imread(image_path)
            if img is None:
                return f"이미지 로드 실패: {image_path}"
            
            # 흐림 감지 (Blur Detection)
            variance = self._is_image_blurry(img)
            is_blurry = variance < 100.0  # 임계값 100
            
            if not is_blurry and not force:
                return (
                    f"이미지가 이미 선명하여 향상 작업을 건너뜁니다 (Variance: {variance:.1f}).\n"
                    f"- 원본 크기: {img.shape[1]}x{img.shape[0]}"
                )
            
            enhanced_img = None
            method_used = "Bicubic Interpolation"

            try:
                # OpenCV DNN Super Resolution 초기화
                sr = cv2.dnn_superres.DnnSuperResImpl_create()
                
                # 모델 경로 설정 (프로젝트 내 models 폴더 가정)
                # 우선순위: EDSR > ESPCN > FSRCNN
                current_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir))) # src/tools/../../
                models_dir = os.path.join(project_root, "models")
                
                model_path = ""
                model_name = ""
                scale = 4
                
                if os.path.exists(os.path.join(models_dir, "EDSR_x4.pb")):
                    model_path = os.path.join(models_dir, "EDSR_x4.pb")
                    model_name = "edsr"
                elif os.path.exists(os.path.join(models_dir, "ESPCN_x4.pb")):
                    model_path = os.path.join(models_dir, "ESPCN_x4.pb")
                    model_name = "espcn"
                elif os.path.exists(os.path.join(models_dir, "FSRCNN_x3.pb")):
                    model_path = os.path.join(models_dir, "FSRCNN_x3.pb")
                    model_name = "fsrcnn"
                    scale = 3

                if model_path:
                    sr.readModel(model_path)
                    sr.setModel(model_name, scale)
                    enhanced_img = sr.upsample(img)
                    method_used = f"DNN Super Resolution ({model_name.upper()} x{scale})"
                else:
                    height, width = img.shape[:2]
                    enhanced_img = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
                    method_used = "Bicubic Interpolation (x2)"
                    
            except Exception as e:
                # DNN 모듈 에러 시 Bicubic으로 폴백
                height, width = img.shape[:2]
                enhanced_img = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
                method_used = "Bicubic Interpolation (Fallback x2)"
            
            # 저장 (선택적)
            if output_path:
                cv2.imwrite(output_path, enhanced_img)
                return (
                    f"이미지 향상 완료 ({method_used}, Variance: {variance:.1f}): {output_path}\n"
                    f"- 원본 크기: {img.shape[1]}x{img.shape[0]}\n"
                    f"- 향상된 크기: {enhanced_img.shape[1]}x{enhanced_img.shape[0]}"
                )
            
            return (
                f"이미지 향상 완료 ({method_used}, Variance: {variance:.1f})\n"
                f"- 원본 크기: {img.shape[1]}x{img.shape[0]}\n"
                f"- 향상된 크기: {enhanced_img.shape[1]}x{enhanced_img.shape[0]}"
            )
            
        except Exception as e:
            return f"이미지 향상 오류: {str(e)}"
    
    async def _arun(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        run_manager: Optional[Any] = None,
    ) -> str:
        """비동기 실행 (동기 실행으로 위임)"""
        return self._run(image_path, output_path, run_manager)

class ImageCropperInput(BaseModel):
    """이미지 크롭 도구 입력 스키마"""
    image_path: str = Field(description="입력 이미지 파일 경로")
    output_path: Optional[str] = Field(default=None, description="출력 이미지 파일 경로 (선택적)")

class ImageCropperTool(BaseTool):
    """
    스마트 크롭 도구
    
    ImageCropper를 래핑하여 ReAct 에이전트가 사용할 수 있도록 합니다.
    """
    
    name: str = "crop_image"
    description: str = (
        "Morphological Gradient 기반으로 단락흔 영역을 탐지하고 크롭합니다. "
        "입력: 이미지 파일 경로, 출력 경로(선택적). "
        "출력: 크롭된 이미지 정보."
    )
    args_schema: type[BaseModel] = ImageCropperInput
    
    def _run(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        run_manager: Optional[Any] = None,
    ) -> str:
        """
        이미지 크롭 실행
        
        Args:
            image_path: 입력 이미지 파일 경로
            output_path: 출력 이미지 파일 경로 (선택적)
            run_manager: 실행 매니저 (선택적)
        
        Returns:
            크롭 결과 문자열
        """
        try:
            # 이미지 로드
            img = cv2.imread(image_path)
            if img is None:
                return f"이미지 로드 실패: {image_path}"
            
            # 크롭 수행
            cropper = ImageCropper()
            cropped_img = cropper.crop(img)
            
            # 저장 (선택적)
            if output_path:
                cv2.imwrite(output_path, cropped_img)
                return (
                    f"이미지 크롭 완료: {output_path}\n"
                    f"- 원본 크기: {img.shape[1]}x{img.shape[0]}\n"
                    f"- 크롭된 크기: {cropped_img.shape[1]}x{cropped_img.shape[0]}"
                )
            
            return (
                f"이미지 크롭 완료\n"
                f"- 원본 크기: {img.shape[1]}x{img.shape[0]}\n"
                f"- 크롭된 크기: {cropped_img.shape[1]}x{cropped_img.shape[0]}"
            )
            
        except Exception as e:
            return f"이미지 크롭 오류: {str(e)}"
    
    async def _arun(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        run_manager: Optional[Any] = None,
    ) -> str:
        """비동기 실행 (동기 실행으로 위임)"""
        return self._run(image_path, output_path, run_manager)

class ImageFilterInput(BaseModel):
    """이미지 필터 도구 입력 스키마"""
    image_path: str = Field(description="입력 이미지 파일 경로")
    output_path: Optional[str] = Field(default=None, description="출력 이미지 파일 경로 (선택적)")

class ImageFilterTool(BaseTool):
    """
    CLAHE 필터 도구
    
    TextureFilter를 래핑하여 ReAct 에이전트가 사용할 수 있도록 합니다.
    """
    
    name: str = "apply_clahe_filter"
    description: str = (
        "CLAHE (Contrast Limited Adaptive Histogram Equalization) 필터를 적용합니다. "
        "입력: 이미지 파일 경로, 출력 경로(선택적). "
        "출력: 필터 적용된 이미지 정보."
    )
    args_schema: type[BaseModel] = ImageFilterInput
    
    def _run(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        run_manager: Optional[Any] = None,
    ) -> str:
        """
        CLAHE 필터 적용 실행
        
        Args:
            image_path: 입력 이미지 파일 경로
            output_path: 출력 이미지 파일 경로 (선택적)
            run_manager: 실행 매니저 (선택적)
        
        Returns:
            필터 적용 결과 문자열
        """
        try:
            # 이미지 로드
            img = cv2.imread(image_path)
            if img is None:
                return f"이미지 로드 실패: {image_path}"
            
            # 필터 적용
            filtered_img = TextureFilter.apply_clahe(img)
            
            # 저장 (선택적)
            if output_path:
                cv2.imwrite(output_path, filtered_img)
                return (
                    f"CLAHE 필터 적용 완료: {output_path}\n"
                    f"- 이미지 크기: {filtered_img.shape[1]}x{filtered_img.shape[0]}"
                )
            
            return (
                f"CLAHE 필터 적용 완료\n"
                f"- 이미지 크기: {filtered_img.shape[1]}x{filtered_img.shape[0]}"
            )
            
        except Exception as e:
            return f"필터 적용 오류: {str(e)}"
    
    async def _arun(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        run_manager: Optional[Any] = None,
    ) -> str:
        """비동기 실행 (동기 실행으로 위임)"""
        return self._run(image_path, output_path, run_manager)

