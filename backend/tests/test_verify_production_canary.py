import jwt
import pytest

from scripts import verify_production_canary as canary

pytestmark = pytest.mark.security


def test_tenant_token_hs256_requires_secret():
    with pytest.raises(ValueError, match="JWT secret is required"):
        canary._tenant_token(
            user_id="u1",
            tenant_id="00000000-0000-0000-0000-000000000001",
            email="canary@example.com",
            jwt_audience="claimflow",
            jwt_algorithm="HS256",
            jwt_secret="",
            jwt_private_key="",
        )


def test_tenant_token_rs256_requires_private_key():
    with pytest.raises(ValueError, match="private key is required"):
        canary._tenant_token(
            user_id="u1",
            tenant_id="00000000-0000-0000-0000-000000000001",
            email="canary@example.com",
            jwt_audience="claimflow",
            jwt_algorithm="RS256",
            jwt_secret="ignored",
            jwt_private_key="",
        )


def test_tenant_token_hs256_encodes_with_expected_claims():
    token = canary._tenant_token(
        user_id="u1",
        tenant_id="00000000-0000-0000-0000-000000000001",
        email="canary@example.com",
        jwt_audience="claimflow",
        jwt_algorithm="HS256",
        jwt_secret="x" * 32,
        jwt_private_key="",
    )
    decoded = jwt.decode(token, "x" * 32, algorithms=["HS256"], audience="claimflow")
    assert decoded["sub"] == "u1"
    assert decoded["tenant_id"] == "00000000-0000-0000-0000-000000000001"
    assert "billing" in decoded["roles"]


def test_compute_go_requires_validate_passed():
    report = {
        "health_ok": True,
        "validate_passed": False,
        "submit_success": True,
        "upload_277_success": True,
        "upload_277_parse": {"claims_updated": 1},
        "upload_835_success": True,
        "claim_final_state": "paid",
        "event_types": ["277ca_received", "payment_posted"],
    }
    assert canary._compute_go(report) is False
