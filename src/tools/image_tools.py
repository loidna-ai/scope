"""
이미지 분석 도구
기존 노드 함수를 ReAct 에이전트 도구로 래핑합니다.
"""
from typing import Optional, Any
import cv2
import numpy as np
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from src.nodes.metrics import MorphologyAnalyzer
# ImageEnhancer는 torch 의존성이 있으므로 지연 로딩
# from src.nodes.enhancement import ImageEnhancer
from src.nodes.crop import ImageCropper
from src.nodes.filter import TextureFilter


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


class ImageEnhancerTool(BaseTool):
    """
    Real-ESRGAN 기반 이미지 향상 도구
    
    ImageEnhancer를 래핑하여 ReAct 에이전트가 사용할 수 있도록 합니다.
    """
    
    name: str = "enhance_image"
    description: str = (
        "Real-ESRGAN을 사용하여 이미지를 4배 초해상도로 향상시킵니다. "
        "입력: 이미지 파일 경로, 출력 경로(선택적). "
        "출력: 향상된 이미지 정보 (크기 등)."
    )
    args_schema: type[BaseModel] = ImageEnhancerInput
    
    def _run(
        self,
        image_path: str,
        output_path: Optional[str] = None,
        run_manager: Optional[Any] = None,
    ) -> str:
        """
        이미지 향상 실행
        
        Args:
            image_path: 입력 이미지 파일 경로
            output_path: 출력 이미지 파일 경로 (선택적)
            run_manager: 실행 매니저 (선택적)
        
        Returns:
            향상 결과 문자열
        """
        try:
            # 이미지 로드
            img = cv2.imread(image_path)
            if img is None:
                return f"이미지 로드 실패: {image_path}"
            
            # 향상 수행 (torch 의존성 확인 - 지연 로딩)
            try:
                # #region agent log
                import json
                import time
                from pathlib import Path
                log_path = Path(__file__).parent.parent.parent / ".cursor" / "debug.log"
                try:
                    with open(log_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"B","location":"image_tools.py:ImageEnhancerTool._run","message":"ImageEnhancer 지연 로딩 시작","data":{},"timestamp":int(time.time()*1000)})+'\n')
                except: pass
                # #endregion
                
                from src.nodes.enhancement import ImageEnhancer
                
                # #region agent log
                try:
                    with open(log_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"B","location":"image_tools.py:ImageEnhancerTool._run","message":"ImageEnhancer 지연 로딩 성공","data":{},"timestamp":int(time.time()*1000)})+'\n')
                except: pass
                # #endregion
                
                enhancer = ImageEnhancer()
                enhanced_img = enhancer.upscale(img)
            except ImportError as e:
                # #region agent log
                try:
                    with open(log_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"B","location":"image_tools.py:ImageEnhancerTool._run","message":"ImageEnhancer 지연 로딩 실패","data":{"error":str(e),"error_type":"ImportError"},"timestamp":int(time.time()*1000)})+'\n')
                except: pass
                # #endregion
                if "torch" in str(e).lower() or "torchvision" in str(e).lower():
                    return f"이미지 향상 도구는 torch/torchvision이 필요합니다. 설치: pip install torch torchvision"
                raise
            except Exception as e:
                # #region agent log
                try:
                    with open(log_path, 'a', encoding='utf-8') as f:
                        f.write(json.dumps({"sessionId":"runtime-test","runId":"run1","hypothesisId":"B","location":"image_tools.py:ImageEnhancerTool._run","message":"ImageEnhancer 실행 중 예상치 못한 오류","data":{"error":str(e),"error_type":type(e).__name__},"timestamp":int(time.time()*1000)})+'\n')
                except: pass
                # #endregion
                raise
            
            # 저장 (선택적)
            if output_path:
                cv2.imwrite(output_path, enhanced_img)
                return (
                    f"이미지 향상 완료: {output_path}\n"
                    f"- 원본 크기: {img.shape[1]}x{img.shape[0]}\n"
                    f"- 향상된 크기: {enhanced_img.shape[1]}x{enhanced_img.shape[0]}"
                )
            
            return (
                f"이미지 향상 완료\n"
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

