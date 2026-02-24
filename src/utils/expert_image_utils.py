"""
전문가 노드 공통 이미지 유틸리티
이미지 로딩, 캐싱, ROI 크롭 및 Enhancement 기능을 제공합니다.
"""
import asyncio
from typing import Tuple, Optional
from src.tools.experts.expert_utils import _load_image_data


class ExpertImageLoader:
    """전문가 노드용 이미지 로더 (캐싱 지원)

    동일한 이미지를 여러 번 로드하는 것을 방지하기 위해 캐싱 기능을 제공합니다.
    max_size로 최대 항목 수를 제한하여 장기 실행 시 메모리 누적을 방지합니다.
    """

    def __init__(self, use_cache: bool = True, max_size: int = 200):
        """
        Args:
            use_cache: 캐싱 사용 여부 (기본값: True)
            max_size: 캐시 최대 항목 수. 초과 시 가장 오래된 항목부터 제거 (기본값: 200)
        """
        self._cache: dict[str, bytes] = {}
        self.use_cache = use_cache
        self.max_size = max_size

    def _evict_if_needed(self):
        """캐시가 max_size를 초과하면 삽입 순서 기준으로 가장 오래된 항목들을 제거합니다."""
        while len(self._cache) >= self.max_size:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

    async def load_images(
        self,
        roi_path: str,
        original_path: str,
        use_cache: Optional[bool] = None,
    ) -> Tuple[bytes, bytes]:
        """ROI 및 원본 이미지를 로드합니다.

        Returns:
            (original_data, roi_data) 튜플
        """
        original_data = await self.load_image(original_path, use_cache)
        roi_data      = await self.load_image(roi_path, use_cache)
        return original_data, roi_data

    async def load_image(self, path: str, use_cache: Optional[bool] = None) -> bytes:
        """단일 이미지를 로드합니다."""
        cache_enabled = use_cache if use_cache is not None else self.use_cache

        if cache_enabled and path in self._cache:
            return self._cache[path]

        # Blocking I/O를 thread로 offload
        data = await asyncio.to_thread(_load_image_data, path)

        if cache_enabled:
            self._evict_if_needed()
            self._cache[path] = data

        return data

    def clear_cache(self):
        """캐시를 비웁니다."""
        self._cache.clear()


# 전역 싱글톤 인스턴스 (기본적으로 캐싱 사용, 최대 200개 항목)
_global_image_loader = ExpertImageLoader(use_cache=True, max_size=200)


def reset_global_image_cache():
    """전역 이미지 캐시를 비웁니다.

    분석 세션이 완료된 후 호출하여 메모리를 해제합니다.
    """
    _global_image_loader.clear_cache()


async def load_expert_images(
    roi_path: str,
    original_path: str,
    use_cache: bool = True,
) -> Tuple[bytes, bytes]:
    """ROI 및 원본 이미지를 로드하는 편의 함수 (전역 로더 사용).

    Returns:
        (original_data, roi_data) 튜플
    """
    if use_cache:
        return await _global_image_loader.load_images(roi_path, original_path, use_cache)
    else:
        loader = ExpertImageLoader(use_cache=False)
        return await loader.load_images(roi_path, original_path, False)
