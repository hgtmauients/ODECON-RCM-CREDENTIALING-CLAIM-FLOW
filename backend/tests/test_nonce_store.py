"""
Unit tests for the in-memory webhook nonce store.

Redis-backed store is integration-tested separately; here we cover the
in-process fallback for correctness and bounded memory.
"""

import asyncio
import pytest

from core import nonce_store


@pytest.mark.asyncio
async def test_first_seen_nonce_returns_false():
    store = nonce_store._MemoryNonceStore()
    assert await store.seen("nonce-A") is False


@pytest.mark.asyncio
async def test_repeat_nonce_returns_true():
    store = nonce_store._MemoryNonceStore()
    assert await store.seen("nonce-B") is False
    assert await store.seen("nonce-B") is True
    assert await store.seen("nonce-B") is True


@pytest.mark.asyncio
async def test_distinct_nonces_independent():
    store = nonce_store._MemoryNonceStore()
    assert await store.seen("a") is False
    assert await store.seen("b") is False
    assert await store.seen("a") is True
    assert await store.seen("b") is True


@pytest.mark.asyncio
async def test_pruning_removes_expired_entries(monkeypatch):
    """After WINDOW_SECONDS, nonces should be eligible for prune."""
    monkeypatch.setattr(nonce_store, "WINDOW_SECONDS", 1)
    store = nonce_store._MemoryNonceStore()
    await store.seen("transient")
    # Force last_prune well in the past so the next call triggers pruning
    store._last_prune = 0
    await asyncio.sleep(1.1)
    # Force another seen() to cause prune
    await store.seen("anything")
    # The transient nonce should be gone
    assert "transient" not in store._seen
