"""
유틸리티 함수 모음
한글 경로 지원 이미지 I/O 및 경로 탐색 함수를 제공합니다.
"""
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Callable, Any, List, Dict
import config
import asyncio
import random
import time
from functools import wraps

# 재시도 로직 공통: 재시도 가능 오류·추가 대기 (async/sync 동일)
_RETRIABLE_ERRORS = [
    "503", "429", "UNAVAILABLE", "overloaded",
    "Value", "empty", "비어있습니다", "응답이", "비어", "FinishReason",
    "ValueError",
    "SSL", "UNEXPECTED_EOF", "10054", "ECONNRESET", "끊겼습니다",
    "EOF while parsing", "json_invalid",  # JSON 중간 잘림(truncation)
]
_ERROR_HANDLERS = {
    "503": 5, "overloaded": 5,
    "SSL": 8, "10054": 8, "ECONNRESET": 8, "끊겼습니다": 8,
}


# === Daily Retry Budget Guard ===
import threading
from datetime import datetime

class RetryBudgetGuard:
    """
    일일 재시도 횟수 제한
    
    Preview 모델의 제한적인 RPD를 보호하기 위해
    하루 최대 재시도 횟수를 추적하고 제한합니다.
    """
    def __init__(self):
        self.daily_retries = 0
        self.last_reset = datetime.now().date()
        self._lock = threading.Lock()
    
    def check_and_increment(self) -> int:
        """
        Thread-safe budget check and increment
        
        Returns:
            현재 재시도 카운트
        
        Raises:
            Exception: Budget 소진 시
        """
        with self._lock:
            today = datetime.now().date()
            if today != self.last_reset:
                self.daily_retries = 0
                self.last_reset = today
            
            if self.daily_retries >= config.GEMINI_DAILY_RETRY_BUDGET:
                raise Exception(
                    f"⛔ Daily retry budget exhausted: {self.daily_retries}/{config.GEMINI_DAILY_RETRY_BUDGET}. "
                    f"Try again tomorrow or increase GEMINI_DAILY_RETRY_BUDGET in config.py"
                )
            
            self.daily_retries += 1
            return self.daily_retries
    
    def get_remaining(self) -> int:
        """남은 재시도 예산 조회"""
        with self._lock:
            return max(0, config.GEMINI_DAILY_RETRY_BUDGET - self.daily_retries)

# Global singleton instance
_retry_budget_guard = RetryBudgetGuard()


def validate_state_keys(
    state: Dict[str, Any], 
    required_keys: List[str],
    context: str = "State"
) -> None:
    """
    State에 필수 키가 있는지 검증 (LangGraph Best Practice)
    
    노드 경계에서 inbound/outbound state를 검증하여
    명확한 에러 메시지를 제공하고 디버깅을 용이하게 합니다.
    
    Args:
        state: 검증할 state dictionary
        required_keys: 필수 키 리스트
        context: 에러 메시지용 컨텍스트
    
    Raises:
        ValueError: 필수 키가 없을 경우
    """
    missing = [key for key in required_keys if not state.get(key)]
    if missing:
        raise ValueError(
            f"{context} validation failed: Missing required keys {missing}"
        )


async def async_retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = 5,
    retriable_errors: Optional[List[str]] = None,
    error_handlers: Optional[dict] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
    context_name: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Exponential Backoff with Jitter + Smart Model Fallback
    
    재시도 가능한 오류 발생 시 지수 백오프 방식으로 재시도합니다.
    
    **New Features (v2.0):**
    - Smart Fallback: 연속 503 에러 시 gemini-2.5-flash로 자동 전환
    - Daily Budget Guard: 일일 재시도 횟수 제한
    - Tier 1 Optimized: Preview 모델 특성 반영한 백오프 시간
    
    Args:
        func: 재시도할 async 함수
        *args: func에 전달할 위치 인자
        max_retries: 최대 재시도 횟수 (기본값: 5, Preview는 3으로 자동 조정)
        retriable_errors: 재시도 가능한 오류 키워드 리스트
        error_handlers: 오류 유형별 추가 대기 시간 매핑
        semaphore: asyncio.Semaphore (동시성 제어용, 선택)
        context_name: 로깅용 컨텍스트 이름 (선택)
        **kwargs: func에 전달할 키워드 인자
                 model_name: Fallback 대상 모델 (자동 전환됨)
    
    Returns:
        함수 실행 결과
    
    Raises:
        Exception: 모든 재시도 실패 시 마지막 예외 전파
    
    Example:
        >>> async def api_call(data, model_name=None):
        ...     return await some_api.call(data, model=model_name)
        >>> 
        >>> result = await async_retry_with_backoff(
        ...     api_call,
        ...     data="test",
        ...     max_retries=3,
        ...     context_name="Worker #1",
        ...     model_name="gemini-3-flash-preview"  # Auto fallback to 2.5-flash on 503
        ... )
    """
    if retriable_errors is None:
        retriable_errors = list(_RETRIABLE_ERRORS)
    if error_handlers is None:
        error_handlers = dict(_ERROR_HANDLERS)

    last_exception = None
    func_name = context_name or (func.__name__ if hasattr(func, '__name__') else 'Unknown')
    
    # === Smart Fallback Tracking ===
    original_model = kwargs.get('model_name', config.GEMINI_MODEL_NAME)
    current_model = original_model
    consecutive_503 = 0
    
    # Tier 1 Preview 모델 최적화
    is_preview_model = 'preview' in str(original_model).lower()
    if is_preview_model and max_retries > 3:
        max_retries = 3  # Preview는 3회로 제한 (RPD 절약)
    
    for retry_attempt in range(max_retries):
        try:
            # === Daily Budget Guard ===
            if retry_attempt > 0 and config.GEMINI_ENABLE_BUDGET_GUARD:
                current_count = _retry_budget_guard.check_and_increment()
                remaining = _retry_budget_guard.get_remaining()
                if remaining < 10:
                    print(f"⚠️ [{func_name}] Retry budget warning: {remaining} retries remaining today")
            
            # === Update Model in kwargs ===
            if 'model_name' in kwargs:
                kwargs['model_name'] = current_model
            
            # === Execute with Semaphore ===
            if semaphore:
                async with semaphore:
                    return await func(*args, **kwargs)
            else:
                return await func(*args, **kwargs)
                
        except Exception as e:
            last_exception = e
            error_msg = str(e)
            
            # === 503 Tracking for Smart Fallback ===
            if "503" in error_msg:
                consecutive_503 += 1
                
                # Smart Fallback after threshold
                if (consecutive_503 >= config.GEMINI_FALLBACK_THRESHOLD 
                    and config.GEMINI_ENABLE_FALLBACK
                    and current_model == original_model):
                    current_model = config.GEMINI_FALLBACK_MODEL
                    consecutive_503 = 0  # Reset counter
                    print(
                        f"🔄 [{func_name}] Switching to fallback model: {current_model} "
                        f"(after {config.GEMINI_FALLBACK_THRESHOLD} consecutive 503s)"
                    )
            else:
                consecutive_503 = 0  # Reset on non-503 errors
            
            # === Check if Retriable ===
            is_retriable = any(code in error_msg for code in retriable_errors)
            
            if is_retriable and retry_attempt < max_retries - 1:
                # === Tier 1 Optimized Backoff ===
                if "503" in error_msg:
                    if is_preview_model:
                        wait_time = 40 * (2 ** retry_attempt)  # 40s, 80s, 160s (Preview 최적화 - 503 에러 완화)
                    else:
                        wait_time = 10 * (2 ** retry_attempt)  # 10s, 20s, 40s
                elif "429" in error_msg:
                    wait_time = 10 * (2 ** retry_attempt)  # RPM/RPD 초과
                else:
                    wait_time = 2 ** retry_attempt  # 기타 오류
                
                # Apply error-specific delays
                for error_key, extra_wait in error_handlers.items():
                    if error_key in error_msg or error_key.lower() in error_msg.lower():
                        wait_time += extra_wait
                        break
                
                # Jitter: 0~50% (increased from 10% for better distribution)
                jitter = random.uniform(0, wait_time * 0.5)
                total_wait = wait_time + jitter
                
                # === Enhanced Logging ===
                model_info = f" [using {current_model}]" if current_model != original_model else ""
                print(
                    f"⚠️ [{func_name}] Retry {retry_attempt + 1}/{max_retries}{model_info}: "
                    f"{error_msg[:100]}... (waiting {total_wait:.2f}s)"
                )
                
                await asyncio.sleep(total_wait)
            else:
                # Non-retriable or max retries reached
                if not is_retriable:
                    print(f"❌ [{func_name}] Non-retriable error: {error_msg[:150]}")
                else:
                    print(f"❌ [{func_name}] Max retries ({max_retries}) exhausted: {error_msg[:150]}")
                raise e
    
    # Safety net (should not reach here)
    if last_exception:
        raise last_exception


def retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = 5,
    retriable_errors: Optional[List[str]] = None,
    error_handlers: Optional[dict] = None,
    context_name: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Exponential Backoff + Jitter를 사용한 **동기** 재시도 로직.
    async_retry_with_backoff와 동일한 retriable_errors·error_handlers를 사용합니다.

    Args:
        func: 재시도할 동기 함수
        *args, **kwargs: func에 전달
        max_retries: 최대 재시도
        retriable_errors: None이면 _RETRIABLE_ERRORS 사용
        error_handlers: None이면 _ERROR_HANDLERS 사용
        context_name: 로깅용 이름

    Returns:
        func 실행 결과

    Raises:
        Exception: 모든 재시도 실패 시 마지막 예외
    """
    if retriable_errors is None:
        retriable_errors = list(_RETRIABLE_ERRORS)
    if error_handlers is None:
        error_handlers = dict(_ERROR_HANDLERS)

    func_name = context_name or (getattr(func, '__name__', None) or 'Unknown')

    for retry_attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e)
            is_retriable = any(c in error_msg for c in retriable_errors)

            if is_retriable and retry_attempt < max_retries - 1:
                wait_time = 2 ** retry_attempt
                for ek, extra in error_handlers.items():
                    if ek in error_msg or ek.lower() in error_msg.lower():
                        wait_time += extra
                        break
                jitter = random.uniform(0, wait_time * 0.1)
                total = wait_time + jitter
                print(f"⚠️ [{func_name}] Retry {retry_attempt + 1}/{max_retries}: {error_msg[:100]}... ({total:.2f}s 대기)")
                time.sleep(total)
            else:
                if not is_retriable:
                    print(f"❌ [{func_name}] Non-retriable: {error_msg[:150]}")
                else:
                    print(f"❌ [{func_name}] Max retries ({max_retries}) exhausted: {error_msg[:150]}")
                raise e
    return None  # unreachable


def find_data_directory(data_dir: Optional[str] = None) -> str:
    """
    data 폴더를 탐색하여 실제 경로를 반환합니다.
    
    현재 위치, 상위 위치 등을 탐색하여 data 폴더를 찾습니다.
    
    Args:
        data_dir: 찾을 디렉토리 이름 (기본값: config.DATA_DIR)
    
    Returns:
        찾은 data 폴더의 절대 경로
    
    Raises:
        ValueError: data 폴더를 찾을 수 없을 때
    """
    if data_dir is None:
        data_dir = config.DATA_DIR
    
    # 여러 가능한 경로 시도
    possible_paths = [
        data_dir,  # 현재 디렉토리
        os.path.join("..", data_dir),  # 상위 디렉토리
        os.path.join(os.path.dirname(os.getcwd()), data_dir),  # 절대 경로
    ]
    
    # 실제 존재하는 경로 찾기
    actual_path = None
    for path in possible_paths:
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path) and os.path.isdir(abs_path):
            actual_path = abs_path
            break
    
    if actual_path is None:
        # 현재 작업 디렉토리 확인
        cwd = os.getcwd()
        # 프로젝트 루트 찾기 시도
        if "notebook" in cwd:
            # notebook 폴더에서 실행 중이면 상위로 이동
            project_root = os.path.dirname(cwd) if os.path.basename(cwd) == "notebook" else cwd
            actual_path = os.path.abspath(os.path.join(project_root, data_dir))
        else:
            actual_path = os.path.abspath(data_dir)
    
    if not os.path.exists(actual_path):
        raise ValueError(f"data 폴더를 찾을 수 없습니다. 시도한 경로: {actual_path}")
    
    return actual_path

def load_image_safe(image_path: str) -> np.ndarray:
    """
    한글 경로 및 특수 문자가 포함된 이미지를 안전하게 로드합니다.
    
    cv2.imread는 한글 경로를 제대로 처리하지 못하므로,
    np.fromfile + cv2.imdecode 패턴을 사용합니다.
    
    Args:
        image_path: 이미지 파일 경로
    
    Returns:
        로드된 이미지 (BGR 형식, numpy.ndarray)
    
    Raises:
        ValueError: 이미지를 로드할 수 없을 때
    """
    import json
    import time
    import os
    
    
    
    # 경로를 Path 객체로 변환하여 정규화
    path = Path(image_path)
    
    if not path.exists():
        raise ValueError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
    
    
    
    # np.fromfile로 바이너리 데이터 읽기 (한글 경로 지원)
    img_array = np.fromfile(str(path), np.uint8)
    
    
    
    
    
    # cv2.imdecode로 이미지 디코딩
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    
    
    
    if img is None:
        raise ValueError(f"이미지를 디코딩할 수 없습니다: {image_path}")
    
    return img

def save_image_safe(image: np.ndarray, output_path: str, quality: int = 95) -> None:
    """
    한글 경로 및 특수 문자가 포함된 경로에 이미지를 안전하게 저장합니다.
    
    cv2.imwrite는 한글 경로를 제대로 처리하지 못하므로,
    cv2.imencode + 파일 쓰기 패턴을 사용합니다.
    
    Args:
        image: 저장할 이미지 (numpy.ndarray)
        output_path: 저장할 파일 경로
        quality: JPEG 품질 (0-100, 기본값: 95). PNG 파일인 경우 무시됨
    
    Raises:
        ValueError: 이미지를 저장할 수 없을 때
    """
    # 출력 디렉토리 생성
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 파일 확장자에 따라 인코딩 방식 결정
    ext = os.path.splitext(output_path)[1].lower()
    
    if ext in ['.jpg', '.jpeg']:
        # JPEG 저장 시 품질 지정
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        success, encoded_img = cv2.imencode(ext, image, encode_params)
    elif ext == '.png':
        # PNG 저장 시 압축 레벨 지정 (0-9, 기본값: 3)
        encode_params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
        success, encoded_img = cv2.imencode(ext, image, encode_params)
    else:
        # 기타 형식은 기본 인코딩
        success, encoded_img = cv2.imencode(ext, image)
    
    if not success:
        raise ValueError(f"이미지 인코딩에 실패했습니다: {output_path}")
    
    # 인코딩된 이미지를 파일로 저장 (한글 경로 지원)
    encoded_img.tofile(output_path)

def crop_roi_from_box(
    image_path: str, 
    box_2d: list, 
    output_path: Optional[str] = None,
    padding_ratio: float = 0.1
) -> str:
    """
    box_2d 좌표(0~1000 정규화)를 사용하여 ROI 크롭
    
    Args:
        image_path: 원본 이미지 경로
        box_2d: [ymin, xmin, ymax, xmax] (0~1000 정규화)
        output_path: 출력 경로 (None이면 임시 파일 생성)
        padding_ratio: 패딩 비율 (기본값: 0.1 = 10%)
    
    Returns:
        크롭된 이미지 경로
        
    Note:
        - box_2d가 [0,0,0,0]이거나 유효하지 않으면 원본 경로 반환
        - 좌표는 0~1000 범위로 정규화되어 있다고 가정
        - 변환 공식: x_pixel = xmin / 1000 * img_width
    """
    import tempfile
    
    # 유효하지 않은 box_2d 체크
    if not box_2d:
        return image_path
    
    # 1. Dictionary 형식 처리 (Pydantic model_dump 결과)
    if isinstance(box_2d, dict):
        ymin = box_2d.get('ymin', 0)
        xmin = box_2d.get('xmin', 0)
        ymax = box_2d.get('ymax', 0)
        xmax = box_2d.get('xmax', 0)
    # 2. List 형식 처리 (기존 방식)
    elif isinstance(box_2d, list) and len(box_2d) == 4:
        ymin, xmin, ymax, xmax = box_2d
    else:
        return image_path
    
    # [0,0,0,0] 체크 (None 케이스)
    if ymin == 0 and xmin == 0 and ymax == 0 and xmax == 0:
        return image_path
    
    # 좌표 유효성 체크 (정규화 좌표 0~1000)
    if xmin >= xmax or ymin >= ymax:
        return image_path

    
    # 이미지 로드
    img = load_image_safe(image_path)
    img_height, img_width = img.shape[:2]
    
    # 정규화된 좌표(0~1000)를 픽셀 좌표로 변환
    x1_pixel = int(xmin / 1000.0 * img_width)
    y1_pixel = int(ymin / 1000.0 * img_height)
    x2_pixel = int(xmax / 1000.0 * img_width)
    y2_pixel = int(ymax / 1000.0 * img_height)
    
    # 패딩 계산
    width = x2_pixel - x1_pixel
    height = y2_pixel - y1_pixel
    padding_x = int(width * padding_ratio)
    padding_y = int(height * padding_ratio)
    
    # 패딩 적용 (이미지 경계 내에서)
    x1_pixel = max(0, x1_pixel - padding_x)
    y1_pixel = max(0, y1_pixel - padding_y)
    x2_pixel = min(img_width, x2_pixel + padding_x)
    y2_pixel = min(img_height, y2_pixel + padding_y)
    
    # ROI 크롭
    cropped_img = img[y1_pixel:y2_pixel, x1_pixel:x2_pixel]
    
    # 출력 경로 설정
    if output_path is None:
        # 임시 파일 생성
        ext = Path(image_path).suffix
        fd, output_path = tempfile.mkstemp(suffix=ext, prefix="roi_crop_")
        os.close(fd)
    
    # 크롭된 이미지 저장
    save_image_safe(cropped_img, output_path)
    
    return output_path

