"""
JWT token revocation store.

Supports:
- Per-token revocation by `jti` (expires automatically at token expiry)
- Per-user revocation watermark ("revoke all tokens issued before timestamp")

Redis-backed when REDIS_URL is configured (multi-worker safe). Falls back to
in-memory state for non-production environments.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "")
ENV = os.getenv("ENV", "development")


class _MemoryRevocationStore:
    def __init__(self) -> None:
        self._revoked_jti: dict[str, float] = {}
        self._user_cutoffs: dict[str, float] = {}
        self._last_prune = time.time()

    async def revoke_jti(self, jti: str, *, exp_ts: float | None = None) -> None:
        expiry = float(exp_ts) if exp_ts is not None else (time.time() + 3600.0)
        self._revoked_jti[jti] = expiry

    async def set_user_cutoff(self, key: str, *, issued_before_ts: float) -> None:
        self._user_cutoffs[key] = float(issued_before_ts)

    async def is_jti_revoked(self, jti: str) -> bool:
        self._prune()
        return jti in self._revoked_jti

    async def get_user_cutoff(self, key: str) -> float | None:
        return self._user_cutoffs.get(key)

    def _prune(self) -> None:
        now = time.time()
        if now - self._last_prune < 60:
            return
        expired = [jti for jti, exp in self._revoked_jti.items() if exp <= now]
        for jti in expired:
            del self._revoked_jti[jti]
        self._last_prune = now


class _RedisRevocationStore:
    def __init__(self, url: str) -> None:
        import redis.asyncio as redis  # type: ignore

        self._redis = redis.from_url(url, decode_responses=True)

    async def revoke_jti(self, jti: str, *, exp_ts: float | None = None) -> None:
        ttl = 3600
        if exp_ts is not None:
            ttl = max(1, int(exp_ts - time.time()))
        await self._redis.set(f"auth:revoke:jti:{jti}", "1", ex=ttl)

    async def set_user_cutoff(self, key: str, *, issued_before_ts: float) -> None:
        await self._redis.set(key, str(float(issued_before_ts)))

    async def is_jti_revoked(self, jti: str) -> bool:
        val = await self._redis.get(f"auth:revoke:jti:{jti}")
        return val is not None

    async def get_user_cutoff(self, key: str) -> float | None:
        val = await self._redis.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except ValueError:
            return None


_store: Optional[object] = None


def _user_cutoff_key(*, tenant_id: str, user_id: str) -> str:
    return f"auth:revoke:after:{tenant_id}:{user_id}"


def _get_store():
    global _store
    if _store is None:
        if REDIS_URL:
            try:
                _store = _RedisRevocationStore(REDIS_URL)
            except Exception as exc:
                if ENV == "production":
                    raise RuntimeError("Token revocation store init failed in production") from exc
                logger.warning("Falling back to memory token revocation store: %s", exc)
                _store = _MemoryRevocationStore()
        else:
            if ENV == "production":
                raise RuntimeError("REDIS_URL required in production for token revocation store")
            _store = _MemoryRevocationStore()
    return _store


def _coerce_timestamp(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def revoke_token_jti(jti: str | None, *, exp: Any = None) -> None:
    if not jti:
        return
    store = _get_store()
    exp_ts = _coerce_timestamp(exp)
    await store.revoke_jti(jti, exp_ts=exp_ts)


async def revoke_user_tokens(*, tenant_id: str, user_id: str, issued_before_ts: float | None = None) -> None:
    store = _get_store()
    cutoff = float(issued_before_ts) if issued_before_ts is not None else time.time()
    await store.set_user_cutoff(_user_cutoff_key(tenant_id=tenant_id, user_id=user_id), issued_before_ts=cutoff)


async def is_token_revoked(*, tenant_id: str, user_id: str, payload: dict[str, Any]) -> bool:
    store = _get_store()
    jti = payload.get("jti")
    if jti and await store.is_jti_revoked(str(jti)):
        return True

    cutoff = await store.get_user_cutoff(_user_cutoff_key(tenant_id=tenant_id, user_id=user_id))
    if cutoff is None:
        return False
    iat_ts = _coerce_timestamp(payload.get("iat"))
    if iat_ts is None:
        return True
    return iat_ts <= cutoff
