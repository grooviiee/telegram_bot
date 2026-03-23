"""파일 기반 LRU 캐시 — 서버 재시작 후에도 캐시 유지."""
import os
import diskcache

class DiskCache:
    def __init__(self, directory: str, max_size: int = 20):
        self.max_size = max_size
        self._cache = diskcache.Cache(directory, size_limit=50 * 1024 * 1024)
        self._order_key = "__key_order__"

    def _get_order(self) -> list:
        return self._cache.get(self._order_key, default=[])

    def _set_order(self, order: list) -> None:
        self._cache.set(self._order_key, order)

    def get(self, key: str):
        value = self._cache.get(key)
        if value is None:
            return None
        order = self._get_order()
        if key in order:
            order.remove(key)
            order.append(key)
            self._set_order(order)
        return value

    def set(self, key: str, value) -> None:
        order = self._get_order()
        if key in order:
            order.remove(key)
        order.append(key)
        while len(order) > self.max_size:
            evicted_key = order.pop(0)
            self._cache.delete(evicted_key)
            print(f"[Cache] '{evicted_key}' 항목이 캐시에서 제거되었습니다.")
        self._set_order(order)
        self._cache.set(key, value)

    def clear(self, key: str = None):
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

    def info(self) -> dict:
        order = self._get_order()
        return {"size": len(order), "max_size": self.max_size, "keys": order}


_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".cache")
dividend_cache      = DiskCache(os.path.join(_CACHE_DIR, "dividend"),      max_size=20)
financials_cache    = DiskCache(os.path.join(_CACHE_DIR, "financials"),    max_size=20)
dividend_json_cache = DiskCache(os.path.join(_CACHE_DIR, "dividend_json"), max_size=20)
business_cache      = DiskCache(os.path.join(_CACHE_DIR, "business"),      max_size=20)
quarterly_financials_cache = DiskCache(os.path.join(_CACHE_DIR, "quarterly_financials"), max_size=20)
quarterly_dividend_cache   = DiskCache(os.path.join(_CACHE_DIR, "quarterly_dividend"),   max_size=20)
valuation_cache            = DiskCache(os.path.join(_CACHE_DIR, "valuation"),            max_size=20)
report_cache               = DiskCache(os.path.join(_CACHE_DIR, "report"),               max_size=10)
