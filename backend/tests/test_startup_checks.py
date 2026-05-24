"""
Tests for startup security configuration validation.
"""

import pytest

from core.startup_checks import validate_adapter_startup_security, validate_api_startup_security

pytestmark = pytest.mark.security


def test_api_validator_rejects_short_hs256_secret_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "too-short",
    }
    with pytest.raises(RuntimeError, match="JWT_SECRET must be at least 32 characters"):
        validate_api_startup_security(env)


def test_api_validator_rejects_missing_jwks_for_rs256_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "RS256",
        "JWT_JWKS_URL": "",
    }
    with pytest.raises(RuntimeError, match="JWT_JWKS_URL is required"):
        validate_api_startup_security(env)


def test_api_validator_rejects_non_https_jwks():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "RS256",
        "JWT_JWKS_URL": "http://issuer.example/jwks.json",
    }
    with pytest.raises(RuntimeError, match="JWT_JWKS_URL must be a valid https URL"):
        validate_api_startup_security(env)


def test_api_validator_rejects_invalid_trusted_proxy_cidrs():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "TRUSTED_PROXY_CIDRS": "10.0.0.0/8,not-a-cidr",
    }
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_CIDRS contains invalid CIDR entry"):
        validate_api_startup_security(env)


def test_api_validator_accepts_valid_production_config():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "RS256",
        "JWT_JWKS_URL": "https://issuer.example/.well-known/jwks.json",
        "TRUSTED_PROXY_CIDRS": "10.0.0.0/8,127.0.0.1/32",
    }
    validate_api_startup_security(env)


def test_adapter_validator_rejects_missing_auth_material_when_required():
    env = {
        "ENV": "production",
        "ADAPTER_REQUIRE_AUTH": "true",
        "ADAPTER_API_KEY": "",
        "ADAPTER_SHARED_SECRET": "",
    }
    with pytest.raises(RuntimeError, match="Adapter auth is required in production"):
        validate_adapter_startup_security(env)


def test_adapter_validator_rejects_invalid_proxy_cidr():
    env = {
        "ENV": "production",
        "ADAPTER_REQUIRE_AUTH": "true",
        "ADAPTER_API_KEY": "k_test",
        "ADAPTER_TRUSTED_PROXY_CIDRS": "10.0.0.0/8,bad-cidr",
    }
    with pytest.raises(RuntimeError, match="ADAPTER_TRUSTED_PROXY_CIDRS contains invalid CIDR entry"):
        validate_adapter_startup_security(env)


def test_adapter_validator_accepts_valid_production_config():
    env = {
        "ENV": "production",
        "ADAPTER_REQUIRE_AUTH": "true",
        "ADAPTER_API_KEY": "k_test",
        "ADAPTER_TRUSTED_PROXY_CIDRS": "10.0.0.0/8",
    }
    validate_adapter_startup_security(env)


def test_validators_skip_non_production_environments():
    validate_api_startup_security({"ENV": "development"})
    validate_adapter_startup_security({"ENV": "test"})
