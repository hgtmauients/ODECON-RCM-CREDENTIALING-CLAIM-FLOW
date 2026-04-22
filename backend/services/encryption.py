"""
ClaimFlow - Encryption service with key versioning support.

Format of stored ciphertext (base64 of):
  Legacy v0: [12-byte nonce][ciphertext]
  Versioned v1+: ['v', version_byte, 12-byte nonce, ciphertext]

Multiple keys can be configured for graceful rotation:
  CLAIMFLOW_ENCRYPTION_KEY        — current/active key (always used for new encryption)
  CLAIMFLOW_ENCRYPTION_KEY_v0..v9 — older keys, kept available for decryption only

When rotating:
  1. Generate a new key, set it as CLAIMFLOW_ENCRYPTION_KEY
  2. Move the previous key to CLAIMFLOW_ENCRYPTION_KEY_v<N> (incrementing N)
  3. Existing ciphertext keeps decrypting from the old slot
  4. Re-encryption can be done lazily by reading + writing each value
"""

import base64
import os
import logging
from typing import Dict, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

VERSIONED_PREFIX = b"v"  # Marker byte for versioned format
CURRENT_VERSION = 1
NONCE_SIZE = 12

_keys: Dict[int, bytes] = {}  # version -> key bytes
_active_version: Optional[int] = None
_initialized = False


def _decode_key(value: str, label: str) -> bytes:
    raw = base64.b64decode(value)
    if len(raw) not in (16, 24, 32):
        raise ValueError(f"{label} must decode to 16, 24, or 32 bytes")
    return raw


def _initialize() -> None:
    """Load keys from env once, on first use."""
    global _keys, _active_version, _initialized
    if _initialized:
        return

    primary = os.getenv("CLAIMFLOW_ENCRYPTION_KEY", "")
    if primary:
        _keys[CURRENT_VERSION] = _decode_key(primary, "CLAIMFLOW_ENCRYPTION_KEY")
        _active_version = CURRENT_VERSION
    else:
        if os.getenv("ENV", "development") != "development":
            raise RuntimeError(
                "CLAIMFLOW_ENCRYPTION_KEY is required in non-development environments. "
                "Generate one with: openssl rand -base64 32"
            )
        logger.warning("CLAIMFLOW_ENCRYPTION_KEY not set - using ephemeral key (dev only)")
        _keys[CURRENT_VERSION] = AESGCM.generate_key(bit_length=256)
        _active_version = CURRENT_VERSION

    # Load historical keys for decryption-only support
    for v in range(0, 10):
        var = f"CLAIMFLOW_ENCRYPTION_KEY_v{v}"
        value = os.getenv(var, "")
        if value:
            _keys[v] = _decode_key(value, var)

    _initialized = True


def _get_key_for_version(version: int) -> bytes:
    _initialize()
    if version not in _keys:
        raise ValueError(f"No encryption key available for version {version}")
    return _keys[version]


async def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string and return base64-encoded ciphertext (versioned)."""
    _initialize()
    assert _active_version is not None
    key = _keys[_active_version]
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    blob = VERSIONED_PREFIX + bytes([_active_version]) + nonce + ct
    return base64.b64encode(blob).decode("ascii")


async def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext, supporting both legacy and versioned format."""
    _initialize()
    raw = base64.b64decode(ciphertext)

    if raw[:1] == VERSIONED_PREFIX and len(raw) > NONCE_SIZE + 2:
        # Versioned format: 'v' + version byte + nonce + ct
        version = raw[1]
        nonce = raw[2:2 + NONCE_SIZE]
        ct = raw[2 + NONCE_SIZE:]
        key = _get_key_for_version(version)
    else:
        # Legacy format: nonce + ct, encrypted with the current key
        nonce = raw[:NONCE_SIZE]
        ct = raw[NONCE_SIZE:]
        key = _get_key_for_version(_active_version) if _active_version is not None else _get_key_for_version(CURRENT_VERSION)

    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return plaintext.decode("utf-8")
