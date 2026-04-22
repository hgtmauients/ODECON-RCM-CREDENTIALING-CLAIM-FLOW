"""
ClaimFlow - Encryption service.
Provides AES-256-GCM envelope encryption for sensitive credential storage.
"""

import base64
import os
from typing import Optional
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ENCRYPTION_KEY = os.getenv("CLAIMFLOW_ENCRYPTION_KEY", "")

_key_bytes: Optional[bytes] = None


def _get_key() -> bytes:
    global _key_bytes
    if _key_bytes is not None:
        return _key_bytes

    if ENCRYPTION_KEY:
        raw = base64.b64decode(ENCRYPTION_KEY)
        if len(raw) not in (16, 24, 32):
            raise ValueError("CLAIMFLOW_ENCRYPTION_KEY must decode to 16, 24, or 32 bytes")
        _key_bytes = raw
    else:
        if os.getenv("ENV", "development") != "development":
            raise RuntimeError(
                "CLAIMFLOW_ENCRYPTION_KEY is required in non-development environments. "
                "Generate one with: openssl rand -base64 32"
            )
        import warnings
        warnings.warn("CLAIMFLOW_ENCRYPTION_KEY not set - using ephemeral key (dev only)", stacklevel=2)
        _key_bytes = AESGCM.generate_key(bit_length=256)
    return _key_bytes


async def encrypt_credential(plaintext: str) -> str:
    """Encrypt a credential string and return base64-encoded ciphertext."""
    key = _get_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ct).decode("ascii")


async def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a base64-encoded ciphertext and return plaintext."""
    key = _get_key()
    aesgcm = AESGCM(key)
    raw = base64.b64decode(ciphertext)
    nonce = raw[:12]
    ct = raw[12:]
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return plaintext.decode("utf-8")
