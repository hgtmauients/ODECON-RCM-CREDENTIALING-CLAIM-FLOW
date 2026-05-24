"""
Unit tests for idempotency key reservation behavior.
"""

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
