"""
유틸리티 함수 모음
코드베이스 전반에서 공통으로 사용되는 유틸리티 함수들을 제공합니다.
각 기능별로 세분화된 모듈에서 임포트하여 노출합니다.
"""

# API 관련 유틸리티 (genai_client.py, api_concurrency.py)
from src.utils.genai_client import get_genai_client
from src.utils.api_concurrency import acquire_api_slot

# 재시도 로직 관련 (retry_utils.py)
from src.utils.retry_utils import (
    async_retry_with_backoff,
    retry_with_backoff,
    RetryBudgetGuard
)

# 파일 시스템 및 경로 관련 (file_utils.py)
from src.utils.file_utils import find_data_directory

# State 검증 관련 (state_utils.py)
from src.utils.state_utils import validate_state_keys

# 이미지 처리 관련 (image_utils.py)
from src.utils.image_utils import (
    load_image_safe,
    save_image_safe,
    crop_roi_from_box
)

__all__ = [
    # API
    "get_genai_client",
    "acquire_api_slot",
    
    # Retry
    "async_retry_with_backoff",
    "retry_with_backoff",
    "RetryBudgetGuard",
    
    # File
    "find_data_directory",
    
    # State
    "validate_state_keys",
    
    # Image
    "load_image_safe",
    "save_image_safe",
    "crop_roi_from_box"
]
