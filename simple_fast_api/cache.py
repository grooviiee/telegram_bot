"""파일 기반 LRU 캐시 — 서버 재시작 후에도 캐시 유지.

diskcache는 디스크(SQLite) I/O이므로, 이벤트 루프를 막지 않도록
모든 공개 메서드는 asyncio.to_thread로 별도 스레드에서 실행한다.
"""
import asyncio
import os
import diskcache
from collections.abc import Awaitable, Callable
from weakref import WeakValueDictionary
from config import (CACHE_SCHEMA_VERSION, DATA_CACHE_TTL_SECONDS,
                    MARKET_CACHE_TTL_SECONDS, AI_CACHE_TTL_SECONDS, NEWS_CACHE_TTL_SECONDS)

class DiskCache:
    def __init__(self, directory: str, max_size: int = 20, ttl: int = DATA_CACHE_TTL_SECONDS):
        self.max_size = max_size
        self.ttl = ttl
        self._locks = WeakValueDictionary()
        self._cache = diskcache.Cache(directory, size_limit=50 * 1024 * 1024)
        self._order_key = "__key_order__"

    def _get_order(self) -> list:
        return [k for k in self._cache.get(self._order_key, default=[]) if k in self._cache]

    def _set_order(self, order: list) -> None:
        self._cache.set(self._order_key, order)

    def _get_sync(self, key: str):
        with self._cache.transact():
            value = self._cache.get(key)
            if not isinstance(value, dict) or value.get("schema") != CACHE_SCHEMA_VERSION or "payload" not in value:
                return None
            order = self._get_order()
            if key in order:
                order.remove(key)
                order.append(key)
                self._set_order(order)
            return value["payload"]

    def _set_sync(self, key: str, value) -> None:
        with self._cache.transact():
            order = self._get_order()
            if key in order:
                order.remove(key)
            order.append(key)
            while len(order) > self.max_size:
                evicted_key = order.pop(0)
                self._cache.delete(evicted_key)
                print(f"[Cache] '{evicted_key}' 항목이 캐시에서 제거되었습니다.")
            self._set_order(order)
            self._cache.set(key, {"schema": CACHE_SCHEMA_VERSION, "payload": value}, expire=self.ttl)

    def _clear_sync(self, key: str = None):
        with self._cache.transact():
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
        order = self._get_order()
        return {"size": len(order), "max_size": self.max_size, "keys": order}

    def lock(self, key: str) -> asyncio.Lock:
        """동일 키의 동시 요청을 합치기 위한 잠금을 반환합니다."""
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get_or_create(self, key: str, loader: Callable[[], Awaitable[dict]]) -> tuple[dict, bool]:
        """유효한 캐시를 재사용하고 동시 미스는 한 번만 수집합니다."""
        async with self.lock(key):
            cached = await self.get(key)
            if cached is not None:
                return cached, True
            result = await loader()
            await self.set(key, result)
            return result, False

    async def get(self, key: str):
        return await asyncio.to_thread(self._get_sync, key)

    async def set(self, key: str, value) -> None:
        await asyncio.to_thread(self._set_sync, key, value)

    async def clear(self, key: str = None):
        return await asyncio.to_thread(self._clear_sync, key)

    async def info(self) -> dict:
        return await asyncio.to_thread(self._info_sync)


_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
dividend_cache      = DiskCache(os.path.join(_CACHE_DIR, "dividend"),      max_size=20)
financials_cache    = DiskCache(os.path.join(_CACHE_DIR, "financials"),    max_size=20)
dividend_json_cache = DiskCache(os.path.join(_CACHE_DIR, "dividend_json"), max_size=20)
business_cache      = DiskCache(os.path.join(_CACHE_DIR, "business"),      max_size=20)
quarterly_financials_cache = DiskCache(os.path.join(_CACHE_DIR, "quarterly_financials"), max_size=20)
quarterly_dividend_cache   = DiskCache(os.path.join(_CACHE_DIR, "quarterly_dividend"),   max_size=20)
valuation_cache            = DiskCache(os.path.join(_CACHE_DIR, "valuation"), max_size=20, ttl=MARKET_CACHE_TTL_SECONDS)
report_cache               = DiskCache(os.path.join(_CACHE_DIR, "report"),               max_size=10, ttl=AI_CACHE_TTL_SECONDS)
buffett_report_cache       = DiskCache(os.path.join(_CACHE_DIR, "buffett_report"),       max_size=10, ttl=AI_CACHE_TTL_SECONDS)
events_cache               = DiskCache(os.path.join(_CACHE_DIR, "events"), max_size=10, ttl=NEWS_CACHE_TTL_SECONDS)

filings_cache = DiskCache(os.path.join(_CACHE_DIR, "filings"), ttl=NEWS_CACHE_TTL_SECONDS)
insider_cache = DiskCache(os.path.join(_CACHE_DIR, "insider"))
insider_ai_cache = DiskCache(os.path.join(_CACHE_DIR, "insider_ai"), ttl=AI_CACHE_TTL_SECONDS)

score_cache = DiskCache(os.path.join(_CACHE_DIR, "score"), ttl=MARKET_CACHE_TTL_SECONDS)
