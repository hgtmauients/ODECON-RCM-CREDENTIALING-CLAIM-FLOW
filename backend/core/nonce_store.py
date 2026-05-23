"""
Replay-protection nonce store.

Backed by Redis when REDIS_URL is set (multi-worker safe), otherwise an
in-process dict with periodic pruning. Nonces expire after WEBHOOK_REPLAY_WINDOW
seconds so the store stays bounded.
"""

import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

WINDOW_SECONDS = int(os.getenv("WEBHOOK_REPLAY_WINDOW", "300"))
REDIS_URL = os.getenv("REDIS_URL", "")
ENV = os.getenv("ENV", "development")


class _MemoryNonceStore:
    def __init__(self) -> None:
        self._seen: dict = {}
        self._last_prune = time.time()

    async def seen(self, key: str) -> bool:
        now = time.time()
        if now - self._last_prune > 60:
            self._prune(now)
            self._last_prune = now
        if key in self._seen:
            return True
        self._seen[key] = now + WINDOW_SECONDS
        return False

    def _prune(self, now: float) -> None:
        expired = [k for k, exp in self._seen.items() if exp < now]
        for k in expired:
            del self._seen[k]


class _RedisNonceStore:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # type: ignore
        self._redis = redis.from_url(url, decode_responses=True)

    async def seen(self, key: str) -> bool:
        full_key = f"webhook:nonce:{key}"
        # SET key 1 NX EX <window>: only set if not exists, with expiry
        result = await self._redis.set(full_key, "1", nx=True, ex=WINDOW_SECONDS)
        # If result is None, key already existed → already seen
        return result is None


_store: Optional[object] = None


def _get_store():
    global _store
    if _store is None:
        if REDIS_URL:
            try:
                _store = _RedisNonceStore(REDIS_URL)
                logger.info("Webhook nonce store: Redis at %s", REDIS_URL)
            except Exception as e:
                if ENV == "production":
                    raise RuntimeError("Redis nonce store init failed in production") from e
                logger.warning("Failed to init Redis nonce store, falling back to memory: %s", e)
                _store = _MemoryNonceStore()
        else:
            if ENV == "production":
                raise RuntimeError("REDIS_URL required in production for replay-safe nonce store")
            _store = _MemoryNonceStore()
    return _store


async def is_replay(nonce: str) -> bool:
    """Return True if this nonce has already been observed within the window."""
    store = _get_store()
    return await store.seen(nonce)
