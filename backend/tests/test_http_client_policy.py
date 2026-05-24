"""
Tests for shared outbound HTTP retry/timeout policy.
"""

import pytest

import core.http_client as policy


@pytest.mark.asyncio
async def test_request_with_retry_retries_on_transport_error_then_succeeds():
    class _FakeResp:
        status_code = 200

    class _FakeClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, **kwargs):
            _ = kwargs
            self.calls += 1
            if self.calls < 3:
                raise policy.httpx.TimeoutException("timeout")
            return _FakeResp()

    fake = _FakeClient()
    resp = await policy.request_with_retry(
        method="GET",
        url="https://example.test",
        max_retries=2,
        retry_backoff_seconds=0,
        client_factory=lambda timeout: fake,
    )
    assert resp.status_code == 200
    assert fake.calls == 3


@pytest.mark.asyncio
async def test_request_with_retry_retries_on_retryable_status_then_succeeds():
    class _FakeResp:
        def __init__(self, code: int):
            self.status_code = code

    class _FakeClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, **kwargs):
            _ = kwargs
            self.calls += 1
            return _FakeResp(503 if self.calls < 3 else 200)

    fake = _FakeClient()
    resp = await policy.request_with_retry(
        method="GET",
        url="https://example.test",
        max_retries=2,
        retry_backoff_seconds=0,
        client_factory=lambda timeout: fake,
    )
    assert resp.status_code == 200
    assert fake.calls == 3


@pytest.mark.asyncio
async def test_request_with_retry_does_not_retry_non_retryable_status():
    class _FakeResp:
        status_code = 400

    class _FakeClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, **kwargs):
            _ = kwargs
            self.calls += 1
            return _FakeResp()

    fake = _FakeClient()
    resp = await policy.request_with_retry(
        method="GET",
        url="https://example.test",
        max_retries=3,
        retry_backoff_seconds=0,
        client_factory=lambda timeout: fake,
    )
    assert resp.status_code == 400
    assert fake.calls == 1


@pytest.mark.asyncio
async def test_request_with_retry_raises_after_retry_budget_exhausted():
    class _FakeClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, **kwargs):
            _ = kwargs
            self.calls += 1
            raise policy.httpx.TransportError("boom")

    fake = _FakeClient()
    with pytest.raises(policy.httpx.TransportError):
        await policy.request_with_retry(
            method="GET",
            url="https://example.test",
            max_retries=2,
            retry_backoff_seconds=0,
            client_factory=lambda timeout: fake,
        )
    assert fake.calls == 3
