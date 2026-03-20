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


_GLOBAL_LOG_FILE: Optional[str] = None

def setup_logger(name: str, level: Optional[str] = None, log_file: Optional[str] = None) -> logging.Logger:
    """
    Expert System용 공통 로거 설정
    
    Args:
        name: 로거 이름 (예: __name__)
        level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
               환경 변수 EXPERT_LOG_LEVEL로 제어 가능
        log_file: 로그를 저장할 파일 경로 (전역 설정됨)
    """
    global _GLOBAL_LOG_FILE
    
    if log_file:
        _GLOBAL_LOG_FILE = log_file
    elif _GLOBAL_LOG_FILE:
        log_file = _GLOBAL_LOG_FILE

    logger = logging.getLogger(name)
    
    # 레벨 설정 (환경 변수 우선)
    log_level = level or os.getenv("EXPERT_LOG_LEVEL", "INFO")
    try:
        logger.setLevel(getattr(logging, log_level.upper()))
    except AttributeError:
        logger.setLevel(logging.INFO)
    
    # 이미 핸들러가 있으면 추가 안 함 (중복 방지)
    if logger.handlers:
        # 파일 핸들러가 없고 log_file이 인자로 전달된 경우 하나 추가
        if log_file and not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
            pass # 아래 로직에서 추가하도록 함
        else:
            return logger
    
    # 콘솔용 깔끔한 포맷터 (메시지만)
    console_formatter = logging.Formatter(fmt='%(message)s')
    
    # 파일용 상세 포맷터 (타임스탬프 등 포함)
    file_formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 콘솔 핸들러 (중복 체크)
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler) for h in logger.handlers):
        console_handler = logging.StreamHandler(sys.__stdout__)
        # StreamToLogger를 통한 중복 출력 방지 필터
        console_handler.addFilter(lambda record: record.funcName != 'write')
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 파일 핸들러 추가
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # 전파 방지 (상위 로거로 로그 전달 안 함)
    logger.propagate = False
    
    return logger
