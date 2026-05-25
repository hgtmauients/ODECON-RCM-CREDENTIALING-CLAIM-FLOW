"""
Simple idempotency-key guard for mutation endpoints.

Current behavior:
- Caller sends Idempotency-Key header.
- First request with a key is accepted and reserved for a short window.
- Duplicate key within the window is rejected with 409.
"""

from __future__ import annotations

import os
import time
from typing import Optional

WINDOW_SECONDS = int(os.getenv("IDEMPOTENCY_WINDOW_SECONDS", "900"))  # 15 minutes
REDIS_URL = os.getenv("REDIS_URL", "")
ENV = os.getenv("ENV", "development")


class _MemoryStore:
    def __init__(self) -> None:
        self._seen: dict[str, float] = {}
        self._last_prune = time.time()

    async def reserve(self, key: str) -> bool:
        now = time.time()
        if now - self._last_prune > 60:
            self._prune(now)
            self._last_prune = now
        if key in self._seen:
            return False
        self._seen[key] = now + WINDOW_SECONDS
        return True

    def _prune(self, now: float) -> None:
        expired = [k for k, exp in self._seen.items() if exp < now]
        for k in expired:
            del self._seen[k]


class _RedisStore:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # type: ignore

        self._redis = redis.from_url(url, decode_responses=True)

    async def reserve(self, key: str) -> bool:
        namespaced = f"idempotency:{key}"
        result = await self._redis.set(namespaced, "1", nx=True, ex=WINDOW_SECONDS)
        return bool(result)


_store: Optional[object] = None


def _get_store():
    global _store
    if _store is None:
        if REDIS_URL:
            _store = _RedisStore(REDIS_URL)
        else:
            if ENV == "production":
                raise RuntimeError("REDIS_URL is required for idempotency in production")
            _store = _MemoryStore()
    return _store


async def reserve_idempotency_key(key: str) -> bool:
    """
    Reserve a caller-supplied idempotency key. Returns True on first use.
    Returns False when the same key already exists in the active window.
    """
    if not key:
        return True
    store = _get_store()
    return await store.reserve(key)
