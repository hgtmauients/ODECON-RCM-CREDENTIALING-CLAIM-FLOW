"""
Tests for startup security configuration validation.
"""

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import base64

from core.startup_checks import validate_adapter_startup_security, validate_api_startup_security

pytestmark = pytest.mark.security


def test_api_validator_rejects_short_hs256_secret_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "too-short",
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
    }
    with pytest.raises(RuntimeError, match="JWT_SECRET must be at least 32 characters"):
        validate_api_startup_security(env)


def test_api_validator_rejects_missing_jwks_for_rs256_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "RS256",
        "JWT_JWKS_URL": "",
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
    }
    with pytest.raises(RuntimeError, match="JWT_JWKS_URL is required"):
        validate_api_startup_security(env)


def test_api_validator_rejects_non_https_jwks():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "RS256",
        "JWT_JWKS_URL": "http://issuer.example/jwks.json",
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
    }
    with pytest.raises(RuntimeError, match="JWT_JWKS_URL must be a valid https URL"):
        validate_api_startup_security(env)


def test_api_validator_rejects_invalid_trusted_proxy_cidrs():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
        "TRUSTED_PROXY_CIDRS": "10.0.0.0/8,not-a-cidr",
    }
    with pytest.raises(RuntimeError, match="TRUSTED_PROXY_CIDRS contains invalid CIDR entry"):
        validate_api_startup_security(env)


def test_api_validator_accepts_valid_production_config():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "RS256",
        "JWT_JWKS_URL": "https://issuer.example/.well-known/jwks.json",
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example,https://admin.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
        "TRUSTED_PROXY_CIDRS": "10.0.0.0/8,127.0.0.1/32",
    }
    validate_api_startup_security(env)


def test_api_validator_rejects_missing_encryption_key_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
    }
    with pytest.raises(RuntimeError, match="CLAIMFLOW_ENCRYPTION_KEY is required"):
        validate_api_startup_security(env)


def test_api_validator_rejects_wildcard_cors_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example,*",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
    }
    with pytest.raises(RuntimeError, match="CORS_ORIGINS cannot contain wildcard"):
        validate_api_startup_security(env)


def test_api_validator_rejects_private_outbound_override_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
        "ALLOW_PRIVATE_OUTBOUND_DESTINATIONS": "true",
    }
    with pytest.raises(RuntimeError, match="ALLOW_PRIVATE_OUTBOUND_DESTINATIONS=true is not allowed"):
        validate_api_startup_security(env)


def test_api_validator_rejects_unknown_sftp_host_keys_override_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
        "SFTP_ALLOW_UNKNOWN_HOST_KEYS": "1",
    }
    with pytest.raises(RuntimeError, match="SFTP_ALLOW_UNKNOWN_HOST_KEYS=true is not allowed"):
        validate_api_startup_security(env)


def test_api_validator_rejects_login_token_body_opt_in_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://:strongpassword@redis.internal:6379/0",
        "AUTH_LOGIN_INCLUDE_TOKEN": "true",
    }
    with pytest.raises(RuntimeError, match="AUTH_LOGIN_INCLUDE_TOKEN=true is not allowed"):
        validate_api_startup_security(env)


def test_api_validator_rejects_redis_url_without_password_in_production():
    env = {
        "ENV": "production",
        "JWT_ALGORITHM": "HS256",
        "JWT_SECRET": "x" * 32,
        "CLAIMFLOW_ENCRYPTION_KEY": base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii"),
        "CORS_ORIGINS": "https://app.claimflow.example",
        "REDIS_URL": "redis://redis.internal:6379/0",
    }
    with pytest.raises(RuntimeError, match="REDIS_URL must include a password"):
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


def test_adapter_validator_rejects_auth_opt_out_in_production():
    env = {
        "ENV": "production",
        "ADAPTER_REQUIRE_AUTH": "false",
        "ADAPTER_API_KEY": "k_test",
    }
    with pytest.raises(RuntimeError, match="ADAPTER_REQUIRE_AUTH=false is not allowed in production"):
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
