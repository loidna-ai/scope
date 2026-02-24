"""
공통 Expert Worker 유틸리티

전문가 노드에서 공통적으로 사용하는 이미지 전처리(ROI 크롭/향상) 및
컴포넌트 분류 로직을 제공합니다.
"""

import os
import asyncio
import shutil
from threading import Lock
from typing import Dict, Any, Optional

import cv2
from google.genai import types

import config
from src.utils import crop_roi_from_box, async_retry_with_backoff, get_genai_client
from src.utils.logging_config import setup_logger
from src.utils.expert_config import LARGE_ROI_THRESHOLD
from src.utils.expert_api_utils import call_classifier_api
from src.utils.expert_image_utils import load_expert_images
from src.models.component_models import ComponentClassification
from src.nodes.enhancement import ImageEnhancer
from src.nodes.enhancement_cache import get_cached_enhancement, save_enhancement_cache

logger = setup_logger(__name__)

# 모듈 레벨 공유 ImageEnhancer 인스턴스 (Lazy Init)
_shared_enhancer = None
_enhancement_lock = Lock()

def _get_enhancer():
    """ImageEnhancer 공유 인스턴스를 반환 (첫 호출 시 초기화)"""
    global _shared_enhancer
    if _shared_enhancer is None:
        _shared_enhancer = ImageEnhancer()
    return _shared_enhancer

async def crop_and_enhance_roi(
    hotspot_id: str,
    image_path: str,
    box_2d: Optional[Dict[str, Any]]
) -> str:
    """
    공통 ROI 크롭 및 Enhancement 로직
    """
    roi_image_path = image_path  # Default fallback
    
    if box_2d:
        logger.debug(f"Worker {hotspot_id}: ROI crop coordinates: {box_2d}")
        try:
            # 임시 파일로 크롭
            cropped_path = await asyncio.to_thread(crop_roi_from_box, image_path, box_2d)
            
            # Enhancement (캐싱 적용)
            logger.info(f"Worker {hotspot_id}: Applying {config.SR_SCALE}x image enhancement...")
            
            # 캐시 확인
            cached_enhanced_path = await asyncio.to_thread(get_cached_enhancement, cropped_path)
            if cached_enhanced_path:
                logger.info(f"Worker {hotspot_id}: Using cached enhancement: {cached_enhanced_path}")
                # 캐시된 파일을 원본 경로로 복사 (기존 동작 유지)
                shutil.copy2(cached_enhanced_path, cropped_path)
                roi_image_path = cropped_path
            else:
                try:
                    xmin, xmax = box_2d.get("xmin", 0), box_2d.get("xmax", 0)
                    ymin, ymax = box_2d.get("ymin", 0), box_2d.get("ymax", 0)
                    area = (xmax - xmin) * (ymax - ymin) if all([xmin, xmax, ymin, ymax]) else 0
                    if area > LARGE_ROI_THRESHOLD:
                        logger.warning(f"Worker {hotspot_id}: Large ROI ({xmax-xmin}x{ymax-ymin}px) detected - Enhancement may take 1-2 mins")
                except Exception:
                    pass
                    
                try:
                    # 1. 크롭된 이미지 로드
                    cropped_img = await asyncio.to_thread(cv2.imread, cropped_path)
                    if cropped_img is None:
                        raise ValueError("크롭된 이미지를 읽을 수 없습니다.")
                    
                    # 2. Enhancement
                    def enhance_image(img, path):
                        with _enhancement_lock:
                            enhancer = _get_enhancer()
                            enhanced_img = enhancer.upscale(img)
                            cv2.imwrite(path, enhanced_img)
                            return path
                    
                    enhanced_path = await asyncio.to_thread(enhance_image, cropped_img, cropped_path)
                    
                    # 3. 캐시 저장
                    await asyncio.to_thread(save_enhancement_cache, cropped_path, enhanced_path)
                    logger.info(f"Worker {hotspot_id}: Enhancement completed: {enhanced_path}")
                    
                except Exception as enh_err:
                    logger.warning(f"Worker {hotspot_id}: Enhancement Failed: {enh_err}")
            
            roi_image_path = cropped_path
        except Exception as e:
            logger.error(f"Worker {hotspot_id}: Crop Failed: {e}")
    
    return roi_image_path


async def enhance_roi_only(
    hotspot_id: str,
    cropped_image_path: str
) -> str:
    """
    크롭된 이미지에 대해 Enhancement만 수행 (전처리기에서 크롭만 완료된 경우).
    
    Args:
        hotspot_id: Hotspot ID
        cropped_image_path: 크롭된 이미지 경로
        
    Returns:
        enhanced_image_path: Enhancement된 이미지 경로 (실패 시 원본 경로)
    """
    enhanced_path = cropped_image_path
    
    try:
        logger.info(f"Worker {hotspot_id}: Applying enhancement to pre-cropped ROI...")
        
        # 캐시 확인
        cached_enhanced_path = await asyncio.to_thread(get_cached_enhancement, cropped_image_path)
        if cached_enhanced_path:
            logger.info(f"Worker {hotspot_id}: Using cached enhancement: {cached_enhanced_path}")
            # 캐시된 파일을 원본 경로로 복사 (기존 동작 유지)
            shutil.copy2(cached_enhanced_path, cropped_image_path)
            enhanced_path = cropped_image_path
        else:
            # 크롭된 이미지 로드
            cropped_img = await asyncio.to_thread(cv2.imread, cropped_image_path)
            if cropped_img is None:
                raise ValueError("크롭된 이미지를 읽을 수 없습니다.")
            
            # Enhancement
            def enhance_image(img, path):
                with _enhancement_lock:
                    enhancer = _get_enhancer()
                    enhanced_img = enhancer.upscale(img)
                    cv2.imwrite(path, enhanced_img)
                    return path
            
            enhanced_path = await asyncio.to_thread(enhance_image, cropped_img, cropped_image_path)
            
            # 캐시 저장
            await asyncio.to_thread(save_enhancement_cache, cropped_image_path, enhanced_path)
            logger.info(f"Worker {hotspot_id}: Enhancement completed: {enhanced_path}")
        
    except Exception as enh_err:
        logger.warning(f"Worker {hotspot_id}: Enhancement Failed: {enh_err}")
    
    return enhanced_path


async def classify_component(
    hotspot_id: str,
    roi_image_path: str,
    image_path: str,
    prompt: str
) -> str:
    """
    공통 컴포넌트 분류 로직
    """
    connection_type = "None"
    
    try:
        logger.info(f"Worker {hotspot_id}: Identifying component type...")
        
        # 공통 이미지 로더 사용
        original_image_data, roi_image_data = await load_expert_images(roi_image_path, image_path)
        
        # 클라이언트 초기화
        client = get_genai_client()
        model_name = os.environ.get("GEMINI_MODEL_NAME", config.GEMINI_MODEL_NAME)
        
        # 파트 구성
        parts = [prompt]
        for img_data in [original_image_data, roi_image_data]:
            parts.append(types.Part.from_bytes(
                data=img_data,
                mime_type="image/jpeg"
            ))
        
        # API 재시도 래퍼
        async def _call_classifier_wrapper(**kwargs):
            return await call_classifier_api(
                client=kwargs["client"],
                model_name=kwargs["model_name"],
                parts=kwargs["parts"],
                response_schema=ComponentClassification,
                context_name=kwargs.get("context_name", f"Worker #{hotspot_id} Classifier")
            )
        
        response = await async_retry_with_backoff(
            _call_classifier_wrapper,
            client=client,
            model_name=model_name,
            parts=parts,
            context_name=f"Worker #{hotspot_id} Classifier",
            max_retries=5
        )
        
        # Pydantic 파싱
        classification = ComponentClassification.model_validate_json(response.text)
        connection_type = classification.deduced_type
        logger.info(f"Worker {hotspot_id}: Component classified as {connection_type} (Confidence: {classification.confidence}%)")
        
    except Exception as e:
        logger.error(f"Worker {hotspot_id}: Classifier final failure: {e}", exc_info=True)
        logger.warning(f"Worker {hotspot_id}: Classification failed, setting type to Unknown")
        connection_type = "Unknown"
    
    return connection_type
