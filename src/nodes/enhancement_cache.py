"""
Enhancement 캐싱 메커니즘

동일한 ROI 이미지에 대한 중복 업스케일링을 방지하기 위한 캐싱 시스템.
파일 기반 캐싱을 사용하여 세션 간에도 캐시를 유지할 수 있습니다.
"""
import os
import hashlib
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Dict
import threading
import time

from src.utils.logging_config import setup_logger
import config

logger = setup_logger(__name__)

# 전역 캐시 딕셔너리 (메모리 캐시)
_enhancement_cache: Dict[str, str] = {}  # {cache_key: enhanced_image_path}
_cache_lock = threading.Lock()

# 캐시 디렉토리
CACHE_DIR = Path(config.OUTPUT_DIR) / ".enhancement_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _get_cache_key(image_path: str, scale: int = None) -> str:
    """
    이미지 경로와 스케일을 기반으로 캐시 키 생성
    
    Args:
        image_path: 원본 이미지 경로
        scale: 업스케일 배율 (기본값: config.SR_SCALE)
    
    Returns:
        캐시 키 (해시값)
    """
    if scale is None:
        scale = config.SR_SCALE
    
    # 파일 경로와 수정 시간을 기반으로 해시 생성
    try:
        stat = os.stat(image_path)
        # 파일 경로 + 크기 + 수정 시간 + 스케일
        key_data = f"{image_path}:{stat.st_size}:{stat.st_mtime}:{scale}"
    except OSError:
        # 파일이 없거나 접근 불가능한 경우 경로만 사용
        key_data = f"{image_path}:{scale}"
    
    return hashlib.md5(key_data.encode()).hexdigest()


def _get_cached_path(cache_key: str) -> Optional[str]:
    """
    캐시된 이미지 경로 반환
    
    Args:
        cache_key: 캐시 키
    
    Returns:
        캐시된 이미지 경로 또는 None (캐시 미스)
    """
    cached_file = CACHE_DIR / f"{cache_key}.jpg"
    
    if cached_file.exists():
        # 파일이 존재하고 유효한지 확인
        try:
            img = cv2.imread(str(cached_file))
            if img is not None:
                return str(cached_file)
        except Exception as e:
            logger.debug(f"캐시 파일 읽기 실패: {e}")
            # 손상된 캐시 파일 삭제
            try:
                cached_file.unlink()
            except Exception:
                pass
    
    return None


def get_cached_enhancement(image_path: str, scale: int = None) -> Optional[str]:
    """
    캐시된 업스케일링 결과를 가져옵니다.
    
    Args:
        image_path: 원본 이미지 경로
        scale: 업스케일 배율 (기본값: config.SR_SCALE)
    
    Returns:
        캐시된 업스케일링된 이미지 경로 또는 None (캐시 미스)
    """
    if not os.path.exists(image_path):
        return None
    
    cache_key = _get_cache_key(image_path, scale)
    
    # 메모리 캐시 확인
    with _cache_lock:
        if cache_key in _enhancement_cache:
            cached_path = _enhancement_cache[cache_key]
            if os.path.exists(cached_path):
                logger.debug(f"메모리 캐시 히트: {image_path}")
                return cached_path
    
    # 파일 캐시 확인
    cached_path = _get_cached_path(cache_key)
    if cached_path:
        logger.info(f"파일 캐시 히트: {image_path} -> {cached_path}")
        # 메모리 캐시에도 추가
        with _cache_lock:
            _enhancement_cache[cache_key] = cached_path
        return cached_path
    
    return None


def save_enhancement_cache(image_path: str, enhanced_image_path: str, scale: int = None) -> str:
    """
    업스케일링 결과를 캐시에 저장합니다.
    
    Args:
        image_path: 원본 이미지 경로
        enhanced_image_path: 업스케일링된 이미지 경로
        scale: 업스케일 배율 (기본값: config.SR_SCALE)
    
    Returns:
        캐시된 파일 경로
    """
    if not os.path.exists(enhanced_image_path):
        return enhanced_image_path
    
    cache_key = _get_cache_key(image_path, scale)
    cached_file = CACHE_DIR / f"{cache_key}.jpg"
    
    try:
        # 캐시 파일로 복사
        import shutil
        shutil.copy2(enhanced_image_path, cached_file)
        
        # 메모리 캐시에도 추가
        with _cache_lock:
            _enhancement_cache[cache_key] = str(cached_file)
        
        logger.debug(f"캐시 저장: {image_path} -> {cached_file}")
        return str(cached_file)
    except Exception as e:
        logger.warning(f"캐시 저장 실패: {e}")
        return enhanced_image_path


def clear_enhancement_cache(max_age_days: int = 7):
    """
    오래된 캐시 파일을 정리합니다.
    
    Args:
        max_age_days: 최대 보관 기간 (일)
    """
    if not CACHE_DIR.exists():
        return
    
    current_time = time.time()
    max_age_seconds = max_age_days * 24 * 60 * 60
    
    cleared_count = 0
    for cache_file in CACHE_DIR.glob("*.jpg"):
        try:
            file_age = current_time - cache_file.stat().st_mtime
            if file_age > max_age_seconds:
                cache_file.unlink()
                cleared_count += 1
        except Exception as e:
            logger.debug(f"캐시 파일 삭제 실패: {e}")
    
    if cleared_count > 0:
        logger.info(f"캐시 정리 완료: {cleared_count}개 파일 삭제")
    
    # 메모리 캐시도 정리
    with _cache_lock:
        to_remove = []
        for cache_key, cached_path in _enhancement_cache.items():
            if not os.path.exists(cached_path):
                to_remove.append(cache_key)
        
        for cache_key in to_remove:
            del _enhancement_cache[cache_key]
        
        if to_remove:
            logger.debug(f"메모리 캐시 정리: {len(to_remove)}개 항목 제거")
