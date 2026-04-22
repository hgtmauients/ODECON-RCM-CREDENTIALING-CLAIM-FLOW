"""
ClaimFlow - Encryption service with key versioning support.

Format of stored ciphertext (base64 of):
  Legacy v0: [12-byte nonce][ciphertext]
  Versioned v1+: ['v', version_byte, 12-byte nonce, ciphertext]

Multiple keys can be configured for graceful rotation:
  CLAIMFLOW_ENCRYPTION_KEY              — current/active key
  CLAIMFLOW_ENCRYPTION_KEY_VERSION      — version slot the active key occupies
                                           (1..255, default 1)
  CLAIMFLOW_ENCRYPTION_KEY_v0..v255     — older keys, kept available for decryption only

When rotating:
  1. Generate a new key.
  2. Move the previous active key into CLAIMFLOW_ENCRYPTION_KEY_v<previous version>.
  3. Set CLAIMFLOW_ENCRYPTION_KEY to the new key.
  4. Bump CLAIMFLOW_ENCRYPTION_KEY_VERSION (e.g. 1 → 2).
  5. Restart the backend.

Existing v1 ciphertext keeps decrypting from the v1 slot; new writes use v2.
Optional lazy re-encrypt: read each encrypted column, write it back with
encrypt_credential() so it gets the new active version. Once everything has
been re-encrypted, you can drop the old v<N> slot.
"""

import base64
import os
import logging
from typing import Dict, Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

VERSIONED_PREFIX = b"v"  # Marker byte for versioned format
NONCE_SIZE = 12

_keys: Dict[int, bytes] = {}  # version -> key bytes
_active_version: Optional[int] = None
_initialized = False


def _decode_key(value: str, label: str) -> bytes:
    raw = base64.b64decode(value)
    if len(raw) not in (16, 24, 32):
        raise ValueError(f"{label} must decode to 16, 24, or 32 bytes")
    return raw


def _resolve_active_version() -> int:
    """Resolve the active key version from env. Defaults to 1 for compat."""
    raw = os.getenv("CLAIMFLOW_ENCRYPTION_KEY_VERSION", "1")
    try:
        version = int(raw)
    except ValueError:
        raise RuntimeError(
            f"CLAIMFLOW_ENCRYPTION_KEY_VERSION must be an integer, got {raw!r}"
        )
    if not (1 <= version <= 255):
        raise RuntimeError(
            "CLAIMFLOW_ENCRYPTION_KEY_VERSION must be between 1 and 255"
        )
    return version


def _initialize() -> None:
    """Load keys from env once, on first use."""
    global _keys, _active_version, _initialized
    if _initialized:
        return

    active_version = _resolve_active_version()
    primary = os.getenv("CLAIMFLOW_ENCRYPTION_KEY", "")
    if primary:
        _keys[active_version] = _decode_key(primary, "CLAIMFLOW_ENCRYPTION_KEY")
        _active_version = active_version
    else:
        env = os.getenv("ENV", "development")
        # Allow ephemeral key in development OR test (CI), but require explicit
        # config in staging/production.
        if env not in ("development", "test"):
            raise RuntimeError(
                "CLAIMFLOW_ENCRYPTION_KEY is required in non-development environments. "
                "Generate one with: openssl rand -base64 32"
            )
        logger.warning(
            "CLAIMFLOW_ENCRYPTION_KEY not set - using ephemeral key (env=%s, version=%d)",
            env, active_version,
        )
        _keys[active_version] = AESGCM.generate_key(bit_length=256)
        _active_version = active_version

    # Load historical keys for decryption-only support across the full v0..v255
    # space. Most deploys will only ever use v0..v9 — the wider range is
    # cheap to scan and avoids the need to bump the loader when a tenant has
    # rotated more than ten times.
    for v in range(0, 256):
        if v == active_version:
            continue  # already loaded as the active key
        var = f"CLAIMFLOW_ENCRYPTION_KEY_v{v}"
        value = os.getenv(var, "")
        if value:
            _keys[v] = _decode_key(value, var)

    logger.info(
        "Encryption initialized: active_version=%d, available_versions=%s",
        _active_version, sorted(_keys.keys()),
    )
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
    """Decrypt a base64-encoded ciphertext, supporting both legacy and versioned format.

    Versioned blobs (v1+) carry the version byte and we look up the matching
    key directly. Legacy blobs (no version byte, pre-rotation format) are
    tried against every available key in priority order: v0 first (the
    canonical "previous active key" slot), then the active key, then the rest.

    With the versioned format + per-version slots, rotating a v1 → v2 key
    simply means installing the new key as v2 (CLAIMFLOW_ENCRYPTION_KEY +
    bumping CLAIMFLOW_ENCRYPTION_KEY_VERSION to 2) while keeping the old key
    parked at CLAIMFLOW_ENCRYPTION_KEY_v1. Old ciphertext continues to
    decrypt; new ciphertext is written under v2.
    """
    _initialize()
    raw = base64.b64decode(ciphertext)

    if raw[:1] == VERSIONED_PREFIX and len(raw) > NONCE_SIZE + 2:
        version = raw[1]
        nonce = raw[2:2 + NONCE_SIZE]
        ct = raw[2 + NONCE_SIZE:]
        key = _get_key_for_version(version)
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode("utf-8")

    # Legacy format: nonce + ct, encrypted with whichever key was active at
    # the time. Try v0 first (canonical "old key" slot) then the rest.
    nonce = raw[:NONCE_SIZE]
    ct = raw[NONCE_SIZE:]

    candidate_versions: list[int] = []
    if 0 in _keys:
        candidate_versions.append(0)
    if _active_version is not None and _active_version not in candidate_versions:
        candidate_versions.append(_active_version)
    for v in sorted(_keys.keys()):
        if v not in candidate_versions:
            candidate_versions.append(v)

    last_err: Exception | None = None
    for v in candidate_versions:
        try:
            aesgcm = AESGCM(_keys[v])
            return aesgcm.decrypt(nonce, ct, None).decode("utf-8")
        except Exception as e:
            last_err = e
            continue

    raise ValueError("Legacy ciphertext could not be decrypted with any configured key") from last_err


async def reencrypt_with_active_key(ciphertext: str) -> str:
    """Decrypt then re-encrypt under the current active version.

    Used by lazy-rotation tooling: read every encrypted column with this,
    persist the result, and after one full sweep the old key version can be
    removed from the env.
    """
    plaintext = await decrypt_credential(ciphertext)
    return await encrypt_credential(plaintext)
