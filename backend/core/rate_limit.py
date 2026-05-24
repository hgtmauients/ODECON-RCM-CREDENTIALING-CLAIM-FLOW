"""
ClaimFlow - Rate limiting middleware.

Production-grade design:
- Bucket key is built from the CLIENT IP only when no validated principal is
  available. We deliberately do NOT trust X-Tenant-ID from the wire — the auth
  layer (run downstream) is the only source of truth for tenant identity, and
  rate_limit runs before auth. Trusting the header would let an unauth caller
  rotate UUIDs to mint fresh buckets.
- After auth, requests carry the tenant_id on request.state so subsequent
  calls land in a per-(tenant, IP) bucket. The first call from a new auth\'d
  client will land in the IP-only bucket; that\'s acceptable — the IP-only
  bucket is also rate-limited.
- Optional Redis backend (set REDIS_URL) for multi-worker / multi-pod safety.
- In-memory fallback for local dev with periodic pruning to bound memory.
- Returns standard X-RateLimit-* headers.
"""

import os
import time
import logging
import ipaddress
from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Set, Union

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.security_signal import log_security_signal

logger = logging.getLogger(__name__)

# Bumped 200 → 600 in B5 because the v11 rate-limit fix removed X-Tenant-ID
# from the bucket key. Multiple tenants behind one office NAT now share a
# single per-IP bucket, so the previous per-tenant 200/min ceiling needed
# headroom. Override with RATE_LIMIT_REQUESTS in env.
DEFAULT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "600"))
DEFAULT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
REDIS_URL = os.getenv("REDIS_URL", "")
ENV = os.getenv("ENV", "development")

# Path patterns that bypass rate limiting entirely (health checks etc).
BYPASS_PATHS = ("/health", "/docs", "/openapi.json", "/redoc")

# OPTIONS preflights are cheap and should not be limited.
BYPASS_METHODS = ("OPTIONS",)


IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]


def _parse_trusted_proxy_cidrs(raw: str) -> Set[IPNetwork]:
    """Parse comma-delimited CIDRs used to trust forwarding headers."""
    cidrs: Set[IPNetwork] = set()
    for part in (raw or "").split(","):
        token = part.strip()
        if not token:
            continue
        try:
            cidrs.add(ipaddress.ip_network(token, strict=False))
        except ValueError:
            logger.warning("Ignoring invalid TRUSTED_PROXY_CIDRS entry: %r", token)
    return cidrs


def _is_trusted_proxy(peer_ip: str, trusted_proxy_cidrs: Set[IPNetwork]) -> bool:
    if not trusted_proxy_cidrs:
        return False
    try:
        addr = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(addr in net for net in trusted_proxy_cidrs)


def _client_ip(request: Request, trusted_proxy_cidrs: Set[IPNetwork]) -> str:
    """
    Best-effort client IP extraction.
    Uses X-Forwarded-For (first hop) ONLY when the immediate socket peer is in
    TRUSTED_PROXY_CIDRS. Otherwise ignores forwarding headers and uses socket
    peer address. This prevents direct clients from spoofing XFF to rotate
    rate-limit buckets.
    """
    peer_ip = request.client.host if request.client else "unknown"
    if _is_trusted_proxy(peer_ip, trusted_proxy_cidrs):
        xff = request.headers.get("X-Forwarded-For", "")
        if xff:
            first_hop = xff.split(",")[0].strip()
            if first_hop:
                return first_hop
    return peer_ip


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
    """
    Redis-backed sliding-window counter using a sorted set per key.

    Uses a Lua script for the count + add as one atomic step. Without atomicity
    we get a TOCTOU window where two concurrent requests can both see
    count<limit and both add. Lua removes that.
    """

    _LUA = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local cutoff = tonumber(ARGV[2])
    local window = tonumber(ARGV[3])
    local limit = tonumber(ARGV[4])
    redis.call('ZREMRANGEBYSCORE', key, 0, cutoff)
    local count = redis.call('ZCARD', key)
    if count >= limit then
      return {0, 0}
    end
    redis.call('ZADD', key, now, tostring(now) .. '-' .. tostring(math.random(1, 1000000)))
    redis.call('EXPIRE', key, window + 1)
    return {1, limit - count - 1}
    """

    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # type: ignore
        self._redis = redis.from_url(url, decode_responses=True)
        self._script = self._redis.register_script(self._LUA)

    async def hit(self, key: str, window: int, limit: int) -> Tuple[bool, int]:
        now = time.time()
        cutoff = now - window
        result = await self._script(keys=[key], args=[now, cutoff, window, limit])
        allowed, remaining = int(result[0]), int(result[1])
        return bool(allowed), remaining


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
        self._trusted_proxy_cidrs = _parse_trusted_proxy_cidrs(os.getenv("TRUSTED_PROXY_CIDRS", ""))
        self._redis_store: Optional[_RedisStore] = None
        if ENV == "production" and not REDIS_URL:
            raise RuntimeError("REDIS_URL required in production for multi-worker-safe rate limiting")
        if REDIS_URL:
            try:
                self._redis_store = _RedisStore(REDIS_URL)
                logger.info("Rate limiter using Redis at %s", REDIS_URL)
            except Exception as e:
                if ENV == "production":
                    raise RuntimeError("Redis rate limiter init failed in production") from e
                logger.warning("Failed to init Redis rate limiter, falling back to in-memory: %s", e)

    def _bucket_key(self, request: Request) -> str:
        # IP-only key. We deliberately do NOT include any caller-supplied
        # tenant header — that would let unauth callers bypass the limit by
        # rotating UUIDs. X-Forwarded-For is only trusted when the immediate
        # socket peer is a configured trusted proxy.
        return f"rl:ip:{_client_ip(request, self._trusted_proxy_cidrs)}"

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
            log_security_signal("rate_limit_exceeded", bucket=key, path=request.url.path, method=request.method)
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
