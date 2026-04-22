"""
ClaimFlow - Rate limiting middleware.

Production-grade design:
- Per-(tenant_id, IP) bucket so a noisy single tenant cannot exhaust capacity
  for everyone, while still preventing per-IP abuse from unauthenticated callers.
- Optional Redis backend (set REDIS_URL) for multi-worker / multi-pod safety.
- In-memory fallback for local dev with periodic pruning to bound memory.
- Returns standard X-RateLimit-* headers.
"""

import os
import time
import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

DEFAULT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "200"))
DEFAULT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
REDIS_URL = os.getenv("REDIS_URL", "")

# Path patterns that bypass rate limiting entirely (health checks etc).
BYPASS_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")

# OPTIONS preflights are cheap and should not be limited.
BYPASS_METHODS = ("OPTIONS",)


def _extract_tenant_id(request: Request) -> Optional[str]:
    """Best-effort tenant ID extraction without parsing the JWT (cheap path)."""
    return request.headers.get("X-Tenant-ID")


class _InMemoryStore:
    """Sliding-window counter with O(N) cleanup; fine for single-process dev."""

    def __init__(self) -> None:
        self._hits: Dict[str, List[float]] = defaultdict(list)
        self._last_prune = time.time()

    def hit(self, key: str, window: int, limit: int) -> Tuple[bool, int]:
        now = time.time()
        bucket = self._hits[key]
        cutoff = now - window
        # Trim
        i = 0
        while i < len(bucket) and bucket[i] <= cutoff:
            i += 1
        if i:
            del bucket[:i]
        if len(bucket) >= limit:
            return False, 0
        bucket.append(now)
        # Periodic pruning to bound memory
        if now - self._last_prune > 300:
            self._prune(now, window)
            self._last_prune = now
        return True, max(0, limit - len(bucket))

    def _prune(self, now: float, window: int) -> None:
        cutoff = now - window
        empty = []
        for k, v in self._hits.items():
            v[:] = [t for t in v if t > cutoff]
            if not v:
                empty.append(k)
        for k in empty:
            del self._hits[k]


class _RedisStore:
    """Redis-backed sliding-window counter using a sorted set per key."""

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # type: ignore
        self._redis = redis.from_url(url, decode_responses=True)

    async def hit(self, key: str, window: int, limit: int) -> Tuple[bool, int]:
        import time as _time
        now = _time.time()
        cutoff = now - window
        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)
        pipe.zcard(key)
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, window + 1)
        _, count, _, _ = await pipe.execute()
        # `count` is the number BEFORE the new add; we just added 1
        if count >= limit:
            # Roll back the add to prevent boundary leaks
            await self._redis.zrem(key, str(now))
            return False, 0
        return True, max(0, limit - count - 1)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        requests_per_window: int = DEFAULT_REQUESTS,
        window_seconds: int = DEFAULT_WINDOW,
    ):
        super().__init__(app)
        self.limit = requests_per_window
        self.window = window_seconds
        self._memory_store = _InMemoryStore()
        self._redis_store: Optional[_RedisStore] = None
        if REDIS_URL:
            try:
                self._redis_store = _RedisStore(REDIS_URL)
                logger.info("Rate limiter using Redis at %s", REDIS_URL)
            except Exception as e:
                logger.warning("Failed to init Redis rate limiter, falling back to in-memory: %s", e)

    def _bucket_key(self, request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"
        tenant_id = _extract_tenant_id(request) or "anon"
        return f"rl:{tenant_id}:{client_ip}"

    async def dispatch(self, request: Request, call_next):
        if request.method in BYPASS_METHODS or any(request.url.path.startswith(p) for p in BYPASS_PATHS):
            return await call_next(request)

        key = self._bucket_key(request)

        if self._redis_store:
            allowed, remaining = await self._redis_store.hit(key, self.window, self.limit)
        else:
            allowed, remaining = self._memory_store.hit(key, self.window, self.limit)

        if not allowed:
            logger.warning("Rate limit exceeded: %s", key)
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please try again later."},
                headers={
                    "Retry-After": str(self.window),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
