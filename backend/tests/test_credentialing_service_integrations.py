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

        async def get(self, _url, params):
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

        async def get(self, _url, params):
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

        async def post(self, _url, json):
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
