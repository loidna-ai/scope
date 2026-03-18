import asyncio
import random
import time
from typing import Optional, Callable, Any, List, Dict, Literal
import os
import config
import threading
from datetime import datetime

from src.utils.api_concurrency import acquire_api_slot

ModelType = Literal["flash", "pro"]


def _infer_model_type(model_name: str | None) -> ModelType:
    """model_name에서 Flash/Pro 구분 (Pro 전용 Rate Limiter 라우팅용)"""
    if not model_name:
        return "flash"
    name_lower = str(model_name).lower()
    if "pro" in name_lower or name_lower == getattr(config, "GEMINI_PRO_MODEL_NAME", "").lower():
        return "pro"
    return "flash"

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
    "429": 5, "RESOURCE_EXHAUSTED": 5,  # Rate limit - 추가 대기
    "SSL": 8, "10054": 8, "ECONNRESET": 8, "끊겼습니다": 8,
}


# === Daily Retry Budget Guard ===
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


async def async_retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = 5,
    retriable_errors: Optional[List[str]] = None,
    error_handlers: Optional[dict] = None,
    semaphore: Optional[asyncio.Semaphore] = None,
    context_name: Optional[str] = None,
    model_type: Optional[ModelType] = None,
    **kwargs
) -> Any:
    """
    Exponential Backoff with Jitter + Smart Model Fallback
    ... (docstring truncated for brevity)
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
    
    # model_type: Pro 전용 Rate Limiter 라우팅 (명시적 전달 또는 model_name 추론)
    effective_model_type: ModelType = model_type or _infer_model_type(original_model)
    
    # Tier 1 Preview 모델 최적화: Flash만 3회 제한, Pro는 429 회복을 위해 5회 유지
    is_preview_model = 'preview' in str(original_model).lower()
    if is_preview_model and effective_model_type == "flash" and max_retries > 3:
        max_retries = 3  # Flash Preview: RPD 절약
    # Pro: max_retries 그대로 (기본 5) - 429 일시적 회복 대비
    
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
            
            # === Execute with Model-Specific Rate Limit (Flash/Pro 분리) ===
            # API 무한 대기 (Hang) 방지를 위한 Timeout 적용
            timeout_seconds = kwargs.pop('timeout', 120)
            
            async def _do_api_call():
                async with acquire_api_slot(model_type=effective_model_type):
                    if semaphore:
                        async with semaphore:
                            return await func(*args, **kwargs)
                    else:
                        return await func(*args, **kwargs)
            
            return await asyncio.wait_for(_do_api_call(), timeout=timeout_seconds)
                
        except asyncio.TimeoutError as e:
            last_exception = e
            error_msg = f"API Timeout (waited {timeout_seconds}s)"
            # Timeout은 503과 유사하게 일시적인 지연으로 간주하여 재시도
            consecutive_503 += 1
            if retry_attempt < max_retries - 1:
                wait_time = 15 * (2 ** retry_attempt)
                jitter = random.uniform(0, wait_time * 0.5)
                total_wait = wait_time + jitter
                print(f"⚠️ [{func_name}] Retry {retry_attempt + 1}/{max_retries} due to {error_msg} (waiting {total_wait:.2f}s)")
                await asyncio.sleep(total_wait)
                continue
            else:
                print(f"❌ [{func_name}] Max retries ({max_retries}) exhausted: {error_msg}")
                raise e
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
            
            # === 429 Fallback for Pro: Vertex AI Pro 할당량 소진 시 Flash로 전환 ===
            if ("429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg) and effective_model_type == "pro":
                if (retry_attempt >= 2 and current_model == original_model 
                    and config.GEMINI_ENABLE_FALLBACK):
                    current_model = config.GEMINI_FALLBACK_MODEL
                    effective_model_type = "flash"
                    print(
                        f"🔄 [{func_name}] Switching to Flash for 429 recovery: {current_model} "
                        f"(after 3 failed Pro attempts)"
                    )
            
            # === Check if Retriable ===
            is_retriable = any(code in error_msg for code in retriable_errors)
            
            if is_retriable and retry_attempt < max_retries - 1:
                # === Tier 1 Optimized Backoff ===
                if "503" in error_msg:
                    if is_preview_model:
                        wait_time = 40 * (2 ** retry_attempt)  # 40s, 80s, 160s (Preview 최적화 - 503 에러 완화)
                    else:
                        wait_time = 10 * (2 ** retry_attempt)  # 10s, 20s, 40s
                elif "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                    # Pro: burst·할당량 제한 더 엄격 → 지수 백오프 강화 (30s, 60s, 120s)
                    if effective_model_type == "pro":
                        wait_time = 30 * (2 ** retry_attempt)  # 30s, 60s, 120s, 240s
                    else:
                        wait_time = 10 * (2 ** retry_attempt)  # 10s, 20s, 40s
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
