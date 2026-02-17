"""
전역 Gemini API 동시성 제어
Hotspot Detector + 모든 Expert 노드(Contact, Deform, Necking)가 공유하는
단일 Rate Limiter 및 Semaphore로 429/503 에러 방지

Note: asyncio.Semaphore는 event loop에 바인딩되므로, Expert 그래프가 각각
asyncio.run()으로 별도 루프에서 실행될 때 "bound to different event loop" 에러 발생.
→ threading.Semaphore 사용 (스레드/루프 무관, asyncio.to_thread로 비블로킹 acquire)

AsyncLimiter: lazy init 패턴으로 실행 시점의 이벤트 루프에 바인딩
"""
from contextlib import asynccontextmanager
from aiolimiter import AsyncLimiter
import asyncio
import threading
import config

# 전역 인스턴스
# - AsyncLimiter: lazy init (실행 시점의 이벤트 루프에 바인딩)
# - threading.Semaphore: 스레드/루프 무관 → Expert의 asyncio.run() 별도 루프에서도 안전
_global_rate_limiter = None
_limiter_lock = threading.Lock()
_global_semaphore = threading.Semaphore(config.GEMINI_TIER1_CONCURRENT)


def _get_rate_limiter() -> AsyncLimiter:
    """
    Lazy-init rate limiter.
    모듈 로드 시점이 아닌 첫 호출 시점에 생성하여
    실행 중인 이벤트 루프에 올바르게 바인딩.
    """
    global _global_rate_limiter
    if _global_rate_limiter is None:
        with _limiter_lock:
            if _global_rate_limiter is None:
                _global_rate_limiter = AsyncLimiter(
                    max_rate=config.GEMINI_TIER1_RPM,
                    time_period=60,
                )
    return _global_rate_limiter


@asynccontextmanager
async def acquire_api_slot():
    """
    API 호출 전 슬롯 획득 (rate limit + concurrency)
    threading.Semaphore: 스레드/event loop 무관하게 동작 (Expert별 asyncio.run() 지원)
    AsyncLimiter: lazy init으로 이벤트 루프 바인딩 문제 방지
    """
    limiter = _get_rate_limiter()
    async with limiter:
        await asyncio.to_thread(_global_semaphore.acquire)
        try:
            yield
        finally:
            _global_semaphore.release()