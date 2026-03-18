"""
전역 Gemini API 동시성 제어 (Flash / Pro 분리)

Flash와 Pro는 Vertex AI에서 별도 할당량을 가지므로, 단일 Rate Limiter 사용은 안티패턴.
- Flash: 30 RPM / 2 concurrent (Hotspot, Preprocessor, Workers 등)
- Pro: 15 RPM / 1 concurrent (Supervisor, Judge, Report Generator 등)

Note: asyncio.Semaphore는 event loop에 바인딩되므로, Expert 그래프가 각각
asyncio.run()으로 별도 루프에서 실행될 때 "bound to different event loop" 에러 발생.
→ asyncio.Semaphore 사용 (동일 루프 내에서만 공유되므로 LangGraph 단일 루프에서는 안전)

ThreadSafeRateLimiter: 여러 이벤트 루프에서 안전하게 작동하는 thread-safe rate limiter
- threading.Lock으로 thread-safe 보장
- collections.deque로 요청 타임스탬프 추적
- Leaky bucket 알고리즘 구현
"""
from contextlib import asynccontextmanager
from collections import deque
from typing import Literal
import asyncio
import threading
import time
import logging
import config

logger = logging.getLogger(__name__)

ModelType = Literal["flash", "pro"]

# Flash / Pro 별도 인스턴스 (모델별 독립 할당량)
_flash_rate_limiter: "ThreadSafeRateLimiter | None" = None
_pro_rate_limiter: "ThreadSafeRateLimiter | None" = None
_flash_semaphore: asyncio.Semaphore | None = None
_pro_semaphore: asyncio.Semaphore | None = None
_limiter_lock = threading.Lock()
_semaphore_lock = threading.Lock()


def _get_rate_limiter(model_type: ModelType) -> "ThreadSafeRateLimiter":
    global _flash_rate_limiter, _pro_rate_limiter
    with _limiter_lock:
        if model_type == "flash":
            if _flash_rate_limiter is None:
                _flash_rate_limiter = ThreadSafeRateLimiter(
                    max_rate=config.GEMINI_TIER1_RPM,
                    time_period=60.0,
                    label="Flash",
                )
            return _flash_rate_limiter
        else:
            if _pro_rate_limiter is None:
                _pro_rate_limiter = ThreadSafeRateLimiter(
                    max_rate=getattr(config, "GEMINI_PRO_RPM", 15),
                    time_period=60.0,
                    label="Pro",
                )
            return _pro_rate_limiter


def _get_semaphore(model_type: ModelType) -> asyncio.Semaphore:
    global _flash_semaphore, _pro_semaphore
    with _semaphore_lock:
        if model_type == "flash":
            if _flash_semaphore is None:
                _flash_semaphore = asyncio.Semaphore(config.GEMINI_TIER1_CONCURRENT)
            return _flash_semaphore
        else:
            if _pro_semaphore is None:
                _pro_semaphore = asyncio.Semaphore(
                    getattr(config, "GEMINI_PRO_CONCURRENT", 1)
                )
            return _pro_semaphore


class ThreadSafeRateLimiter:
    """
    Thread-safe rate limiter that works across multiple event loops.
    
    Leaky bucket algorithm implementation using threading.Lock for thread safety.
    Tracks request timestamps in a deque and enforces rate limits over a time window.
    
    This limiter can be safely shared across multiple asyncio event loops,
    unlike AsyncLimiter which is bound to a single event loop.
    """
    
    def __init__(self, max_rate: int, time_period: float = 60.0, label: str = ""):
        """
        Initialize thread-safe rate limiter.
        
        Args:
            max_rate: Maximum number of requests allowed in time_period
            time_period: Time window in seconds (default: 60.0)
            label: 로깅용 라벨 (예: "Flash", "Pro")
        """
        self.max_rate = max_rate
        self.time_period = time_period
        self._label = label or "API"
        self._lock = threading.Lock()
        self._requests = deque()  # timestamps
        # Minimum interval between requests to prevent burst (60 seconds / max_rate)
        # This ensures requests are evenly distributed over the time window
        # NOTE: 최소 간격 체크는 동시 요청이 많을 때 병목을 유발하므로 비활성화
        # Leaky bucket 알고리즘만으로도 충분히 Rate Limit을 지킬 수 있음
        self._min_interval = 0.0  # 비활성화: time_period / max_rate if max_rate > 0 else 0.0
    
    def _cleanup_old_requests(self, now: float):
        """
        Remove requests older than time_period.
        
        Args:
            now: Current timestamp
        """
        while self._requests and (now - self._requests[0]) > self.time_period:
            self._requests.popleft()
    
    def _try_acquire_and_record(self) -> tuple[bool, float]:
        """
        Atomically check if request can proceed and record timestamp if proceeding.
        
        This combines _can_proceed() and _record_request() into a single atomic operation
        to prevent race conditions where multiple threads pass _can_proceed() checks
        before any of them records their request.
        
        Also enforces minimum interval between requests to prevent burst rate limits.
        
        Returns:
            (can_proceed: bool, wait_time: float)
            - can_proceed: True if request was recorded and can proceed, False if needs to wait
            - wait_time: Seconds to wait before proceeding (0.0 if can_proceed is True)
        """
        with self._lock:
            now = time.time()
            self._cleanup_old_requests(now)
            current_count = len(self._requests)
            
            # Check minimum interval to prevent burst (if we have recent requests)
            # NOTE: 최소 간격 체크는 동시 요청이 많을 때 병목을 유발하므로 완화
            # 현재 요청 수가 제한의 80% 미만일 때만 최소 간격 체크 수행
            if (self._requests and self._min_interval > 0 
                and current_count < self.max_rate * 0.8):
                time_since_last = now - self._requests[-1]
                if time_since_last < self._min_interval:
                    wait_time = self._min_interval - time_since_last
                    return False, wait_time
            
            if current_count < self.max_rate:
                # Can proceed immediately - record timestamp atomically
                self._requests.append(now)
                count_after = len(self._requests)
                logger.debug(f"[RateLimiter:{self._label}] Request recorded. Current count: {count_after}/{self.max_rate}")
                if count_after >= self.max_rate * 0.8:  # 80% 이상 사용 시 경고
                    logger.warning(f"[RateLimiter:{self._label}] Rate limit approaching: {count_after}/{self.max_rate} requests in last 60s")
                return True, 0.0
            
            # Need to wait until oldest request expires
            oldest_time = self._requests[0]
            wait_time = self.time_period - (now - oldest_time)
            if wait_time > 0:
                return False, wait_time
            else:
                # Oldest expired, can proceed - record timestamp atomically
                self._requests.popleft()
                self._requests.append(now)
                count_after = len(self._requests)
                logger.debug(f"[RateLimiter:{self._label}] Request recorded. Current count: {count_after}/{self.max_rate}")
                return True, 0.0
    
    @asynccontextmanager
    async def acquire(self):
        """
        Async context manager for rate limiting.
        
        Usage:
            async with limiter.acquire():
                # API call here
        """
        loop_count = 0
        while True:
            can_proceed, wait_time = self._try_acquire_and_record()
            if can_proceed:
                # Timestamp already recorded atomically in _try_acquire_and_record()
                if loop_count > 0:
                    logger.debug(f"[RateLimiter:{self._label}] Acquired after {loop_count} wait cycles")
                break
            loop_count += 1
            logger.warning(f"[RateLimiter:{self._label}] Rate limit reached ({self.max_rate} RPM), waiting {wait_time:.2f}s (attempt {loop_count})")
            await asyncio.sleep(wait_time)
        
        try:
            yield
        finally:
            # Request completed, cleanup happens in next acquire
            pass


@asynccontextmanager
async def acquire_api_slot(model_type: ModelType = "flash"):
    """
    API 호출 전 슬롯 획득 (rate limit + concurrency)
    
    Flash와 Pro는 Vertex AI에서 별도 할당량을 가지므로 분리된 풀 사용.
    
    Args:
        model_type: "flash" | "pro"
            - flash: 30 RPM, 2 concurrent (Hotspot, Preprocessor, Workers 등)
            - pro: 15 RPM, 1 concurrent (Supervisor, Judge, Report Generator 등)
    
    Usage:
        async with acquire_api_slot("flash"):
            await call_flash_api()
        async with acquire_api_slot("pro"):
            await call_pro_api()
    """
    sem = _get_semaphore(model_type)
    await sem.acquire()
    try:
        limiter = _get_rate_limiter(model_type)
        async with limiter.acquire():
            yield
    finally:
        sem.release()