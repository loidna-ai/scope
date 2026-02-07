"""
Necking Expert 로깅 설정 모듈

Production-ready 로깅 시스템 제공
- 환경 변수로 로그 레벨 제어
- 구조화된 로그 포맷
- 파일 및 콘솔 출력 지원
"""
import logging
import sys
import os
from typing import Optional


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """
    Expert System용 공통 로거 설정
    
    Args:
        name: 로거 이름 (예: __name__)
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               환경 변수 EXPERT_LOG_LEVEL로 제어 가능
    
    Returns:
        설정된 Logger 객체
    
    Example:
        >>> logger = setup_logger(__name__)
    """
    logger = logging.getLogger(name)
    
    # 레벨 설정 (환경 변수 우선)
    log_level = level or os.getenv("EXPERT_LOG_LEVEL", "INFO")
    try:
        logger.setLevel(getattr(logging, log_level.upper()))
    except AttributeError:
        logger.setLevel(logging.INFO)
    
    # 이미 핸들러가 있으면 추가 안 함 (중복 방지)
    if logger.handlers:
        return logger
    
    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    
    # 포맷터 (타임스탬프, 레벨, 모듈, 함수명, 메시지)
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)
    
    logger.addHandler(console_handler)
    
    # 전파 방지 (상위 로거로 로그 전달 안 함)
    logger.propagate = False
    
    return logger
