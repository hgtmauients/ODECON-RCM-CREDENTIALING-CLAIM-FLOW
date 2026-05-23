import pytest

import services.credentialing_service as credentialing_module
from services.credentialing_service import CredentialingService


@pytest.mark.asyncio
async def test_state_license_verification_fails_closed_without_provider(monkeypatch):
    monkeypatch.delenv("STATE_LICENSE_PROVIDER_URL", raising=False)
    svc = CredentialingService()

    result = await svc.verify_state_license(
        state_code="HI",
        license_number="HI-12345",
        provider_name="Test Provider",
        dob="1980-01-01",
    )

    assert result["verified"] is False
    assert result["requires_manual_review"] is True
    assert result["source"] == "manual_policy"
    assert result["error"] == "state_license_provider_not_configured"


@pytest.mark.asyncio
async def test_background_check_fails_closed_without_provider(monkeypatch):
    monkeypatch.delenv("BACKGROUND_CHECK_PROVIDER_URL", raising=False)
    svc = CredentialingService()

    result = await svc.run_background_check(
        first_name="Test",
        last_name="Provider",
        dob="1980-01-01",
    )

    assert result["verified"] is False
    assert result["clear"] is False
    assert result["recommendation"] == "requires_review"
    assert result["source"] == "manual_policy"
    assert result["error"] == "background_check_provider_not_configured"


@pytest.mark.asyncio
async def test_state_license_non_200_requires_manual_review(monkeypatch):
    monkeypatch.setenv("STATE_LICENSE_PROVIDER_URL", "https://license.example/verify")

    class _FakeResp:
        status_code = 503

        @staticmethod
        def json():
            return {}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url=None, params=None, json=None, headers=None, **kwargs):
            assert method == "GET"
            _ = url, json, headers, kwargs
            assert params["state"] == "HI"
            return _FakeResp()

    monkeypatch.setattr(credentialing_module.httpx, "AsyncClient", lambda timeout: _FakeClient())
    svc = CredentialingService()
    result = await svc.verify_state_license("HI", "HI-12345", "Test Provider", "1980-01-01")

    assert result["verified"] is False
    assert result["requires_manual_review"] is True
    assert result["source"] == "state_license_provider"
    assert result["error"] == "state_license_lookup_failed_503"


@pytest.mark.asyncio
async def test_state_license_infers_verified_from_active_status(monkeypatch):
    monkeypatch.setenv("STATE_LICENSE_PROVIDER_URL", "https://license.example/verify")

    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ACTIVE", "verified": False}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url=None, params=None, json=None, headers=None, **kwargs):
            assert method == "GET"
            _ = url, json, headers, kwargs
            assert params["license_number"] == "HI-12345"
            return _FakeResp()

    monkeypatch.setattr(credentialing_module.httpx, "AsyncClient", lambda timeout: _FakeClient())
    svc = CredentialingService()
    result = await svc.verify_state_license("HI", "HI-12345", "Test Provider", "1980-01-01")

    assert result["verified"] is True
    assert result["requires_manual_review"] is False
    assert result["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_background_check_non_200_requires_review(monkeypatch):
    monkeypatch.setenv("BACKGROUND_CHECK_PROVIDER_URL", "https://bg.example/check")

    class _FakeResp:
        status_code = 500

        @staticmethod
        def json():
            return {}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url=None, params=None, json=None, headers=None, **kwargs):
            assert method == "POST"
            _ = url, params, headers, kwargs
            assert json["first_name"] == "Test"
            return _FakeResp()

    monkeypatch.setattr(credentialing_module.httpx, "AsyncClient", lambda timeout: _FakeClient())
    svc = CredentialingService()
    result = await svc.run_background_check("Test", "Provider", "1980-01-01")

    assert result["verified"] is False
    assert result["clear"] is False
    assert result["recommendation"] == "requires_review"
    assert result["source"] == "background_check_provider"
    assert result["error"] == "background_check_lookup_failed_500"


@pytest.mark.asyncio
async def test_state_license_includes_adapter_auth_headers(monkeypatch):
    monkeypatch.setenv("STATE_LICENSE_PROVIDER_URL", "https://adapter.example/license/verify")
    monkeypatch.setenv("ADAPTER_API_KEY", "api_key")
    monkeypatch.setenv("ADAPTER_SHARED_SECRET", "shared_secret")

    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ACTIVE", "verified": True}

    class _FakeClient:
        seen_headers = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url=None, params=None, json=None, headers=None, **kwargs):
            _ = method, url, params, json, kwargs
            self.seen_headers = headers
            return _FakeResp()

    fake = _FakeClient()
    monkeypatch.setattr(credentialing_module.httpx, "AsyncClient", lambda timeout: fake)
    svc = CredentialingService()
    result = await svc.verify_state_license("HI", "HI-12345", "Test Provider", "1980-01-01")

    assert result["verified"] is True
    assert fake.seen_headers["X-Adapter-Key"] == "api_key"
    assert "X-Adapter-Timestamp" in fake.seen_headers
    assert "X-Adapter-Signature" in fake.seen_headers


@pytest.mark.asyncio
async def test_background_check_retries_on_timeout_then_succeeds(monkeypatch):
    monkeypatch.setenv("BACKGROUND_CHECK_PROVIDER_URL", "https://adapter.example/background/check")
    monkeypatch.setenv("ADAPTER_CLIENT_MAX_RETRIES", "2")
    monkeypatch.setenv("ADAPTER_CLIENT_RETRY_BACKOFF_SECONDS", "0")

    class _FakeResp:
        status_code = 200

        @staticmethod
        def json():
            return {"verified": True, "clear": True, "findings": []}

    class _FakeClient:
        calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url=None, params=None, json=None, headers=None, **kwargs):
            _ = method, url, params, json, headers, kwargs
            self.calls += 1
            if self.calls < 3:
                raise credentialing_module.httpx.TimeoutException("timeout")
            return _FakeResp()

    fake = _FakeClient()
    monkeypatch.setattr(credentialing_module.httpx, "AsyncClient", lambda timeout: fake)
    svc = CredentialingService()
    result = await svc.run_background_check("Test", "Provider", "1980-01-01")

    assert result["verified"] is True
    assert result["clear"] is True
    assert fake.calls == 3
