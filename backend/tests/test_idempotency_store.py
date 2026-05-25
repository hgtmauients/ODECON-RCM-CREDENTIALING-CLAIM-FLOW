"""
Unit tests for idempotency key reservation behavior.
"""

import asyncio

import pytest

from core import idempotency


@pytest.mark.asyncio
async def test_reserve_idempotency_key_allows_first_and_blocks_duplicate():
    # Use isolated in-memory store for deterministic behavior.
    idempotency._store = idempotency._MemoryStore()
    key = "tenant-a:create_claim:abc123"
    first = await idempotency.reserve_idempotency_key(key)
    second = await idempotency.reserve_idempotency_key(key)
    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_empty_idempotency_key_is_treated_as_noop():
    idempotency._store = idempotency._MemoryStore()
    assert await idempotency.reserve_idempotency_key("") is True


@pytest.mark.asyncio
async def test_reserve_idempotency_key_concurrent_calls_only_allow_one():
    idempotency._store = idempotency._MemoryStore()
    key = "tenant-a:submit_claim_batch:race-key"
    results = await asyncio.gather(
        idempotency.reserve_idempotency_key(key),
        idempotency.reserve_idempotency_key(key),
    )
    assert sorted(results) == [False, True]


def test_get_store_requires_redis_in_production(monkeypatch):
    idempotency._store = None
    monkeypatch.setattr(idempotency, "ENV", "production")
    monkeypatch.setattr(idempotency, "REDIS_URL", "")

    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        idempotency._get_store()
