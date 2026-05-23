import pytest

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
