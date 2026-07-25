"""파일 기반 LRU 캐시 — 서버 재시작 후에도 캐시 유지.

diskcache는 디스크(SQLite) I/O이므로, 이벤트 루프를 막지 않도록
모든 공개 메서드는 asyncio.to_thread로 별도 스레드에서 실행한다.
"""
import asyncio
import os
import diskcache

from config import (
    CACHE_SIZE_DART, CACHE_SIZE_REPORT, CACHE_SIZE_INSIDER, CACHE_SIZE_EVENTS,
    CACHE_TTL_DART, CACHE_TTL_VALUATION, CACHE_TTL_REPORT,
    CACHE_TTL_INSIDER, CACHE_TTL_EVENTS,
)


class DiskCache:
    """LRU + TTL 디스크 캐시.

    max_size는 LRU 축출 기준 항목 수, expire는 항목별 TTL(초, None이면 무기한).
    순서 목록(`__key_order__`) 자체에는 TTL을 걸지 않는다 — 만료되면 전체 LRU
    상태를 잃기 때문이다.
    """

    def __init__(self, directory: str, max_size: int = 20, expire: int | None = None):
        self.max_size = max_size
        self.expire = expire
        self._cache = diskcache.Cache(directory, size_limit=50 * 1024 * 1024)
        self._order_key = "__key_order__"

    def _get_order(self) -> list:
        return self._cache.get(self._order_key, default=[])

    def _set_order(self, order: list) -> None:
        self._cache.set(self._order_key, order)

    def _get_sync(self, key: str):
        value = self._cache.get(key)
        if value is None:
            # TTL로 만료된 항목은 순서 목록에도 남지 않도록 정리한다.
            order = self._get_order()
            if key in order:
                order.remove(key)
                self._set_order(order)
            return None
        order = self._get_order()
        if key in order:
            order.remove(key)
            order.append(key)
            self._set_order(order)
        return value

    def _set_sync(self, key: str, value) -> None:
        order = self._get_order()
        if key in order:
            order.remove(key)
        order.append(key)
        while len(order) > self.max_size:
            evicted_key = order.pop(0)
            self._cache.delete(evicted_key)
            print(f"[Cache] '{evicted_key}' 항목이 캐시에서 제거되었습니다.")
        self._set_order(order)
        self._cache.set(key, value, expire=self.expire)

    def _clear_sync(self, key: str = None):
        if key:
            order = self._get_order()
            if key not in order:
                return False
            order.remove(key)
            self._set_order(order)
            self._cache.delete(key)
            return True
        else:
            self._cache.clear()
            return True

    def _info_sync(self) -> dict:
        # 만료된 키는 아직 순서 목록에 남아 있을 수 있으므로 걸러서 보고한다.
        keys = [k for k in self._get_order() if k in self._cache]
        return {
            "size": len(keys),
            "max_size": self.max_size,
            "ttl": self.expire,
            "keys": keys,
        }

    async def get(self, key: str):
        return await asyncio.to_thread(self._get_sync, key)

    async def set(self, key: str, value) -> None:
        await asyncio.to_thread(self._set_sync, key, value)

    async def clear(self, key: str = None):
        return await asyncio.to_thread(self._clear_sync, key)

    async def info(self) -> dict:
        return await asyncio.to_thread(self._info_sync)


_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")

# DART 원본 데이터 — 재조회 비용은 무료 API 호출뿐이라 TTL을 길게 둔다.
dividend_cache      = DiskCache(os.path.join(_CACHE_DIR, "dividend"),      max_size=CACHE_SIZE_DART, expire=CACHE_TTL_DART)
financials_cache    = DiskCache(os.path.join(_CACHE_DIR, "financials"),    max_size=CACHE_SIZE_DART, expire=CACHE_TTL_DART)
dividend_json_cache = DiskCache(os.path.join(_CACHE_DIR, "dividend_json"), max_size=CACHE_SIZE_DART, expire=CACHE_TTL_DART)
business_cache      = DiskCache(os.path.join(_CACHE_DIR, "business"),      max_size=CACHE_SIZE_DART, expire=CACHE_TTL_DART)
quarterly_financials_cache = DiskCache(os.path.join(_CACHE_DIR, "quarterly_financials"), max_size=CACHE_SIZE_DART, expire=CACHE_TTL_DART)
quarterly_dividend_cache   = DiskCache(os.path.join(_CACHE_DIR, "quarterly_dividend"),   max_size=CACHE_SIZE_DART, expire=CACHE_TTL_DART)

# 주가 기반 지표 — TTL이 없으면 최초 조회 시점 가격이 영구 고정된다.
valuation_cache = DiskCache(os.path.join(_CACHE_DIR, "valuation"), max_size=CACHE_SIZE_DART, expire=CACHE_TTL_VALUATION)

# LLM 결과 — 축출·만료가 곧 재과금이므로 크기를 넉넉히, TTL을 길게 잡는다.
report_cache         = DiskCache(os.path.join(_CACHE_DIR, "report"),         max_size=CACHE_SIZE_REPORT,  expire=CACHE_TTL_REPORT)
buffett_report_cache = DiskCache(os.path.join(_CACHE_DIR, "buffett_report"), max_size=CACHE_SIZE_REPORT,  expire=CACHE_TTL_REPORT)
insider_cache        = DiskCache(os.path.join(_CACHE_DIR, "insider"),        max_size=CACHE_SIZE_INSIDER, expire=CACHE_TTL_INSIDER)
events_cache         = DiskCache(os.path.join(_CACHE_DIR, "events"),         max_size=CACHE_SIZE_EVENTS,  expire=CACHE_TTL_EVENTS)
