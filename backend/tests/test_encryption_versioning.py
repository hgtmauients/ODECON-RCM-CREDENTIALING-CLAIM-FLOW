"""
Unit tests for the encryption module's versioning + key rotation.

Verifies:
- Versioned encrypt/decrypt roundtrip
- Legacy ciphertext (pre-v1, no version byte) decrypts using the active key
- Legacy ciphertext can be decrypted by a v0 historical key after rotation
"""

import base64
import os
import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


@pytest.fixture(autouse=True)
def reset_encryption_module():
    """Reload the encryption module between tests so env vars take effect."""
    import importlib
    import services.encryption as enc
    yield
    importlib.reload(enc)


@pytest.mark.asyncio
async def test_versioned_roundtrip(monkeypatch):
    """A value encrypted now should decrypt cleanly with the same key."""
    key_b64 = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", key_b64)
    monkeypatch.setenv("ENV", "test")

    import importlib, services.encryption as enc
    importlib.reload(enc)

    ct = await enc.encrypt_credential("hello world")
    pt = await enc.decrypt_credential(ct)
    assert pt == "hello world"


@pytest.mark.asyncio
async def test_legacy_blob_decrypts_with_active_key(monkeypatch):
    """A legacy (pre-v1) ciphertext format should decrypt with the active key."""
    raw_key = AESGCM.generate_key(bit_length=256)
    key_b64 = base64.b64encode(raw_key).decode()
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", key_b64)
    monkeypatch.setenv("ENV", "test")

    # Build a legacy blob: nonce(12) + ct, no version byte
    aesgcm = AESGCM(raw_key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, b"legacy value", None)
    legacy_b64 = base64.b64encode(nonce + ct).decode()

    import importlib, services.encryption as enc
    importlib.reload(enc)

    pt = await enc.decrypt_credential(legacy_b64)
    assert pt == "legacy value"


@pytest.mark.asyncio
async def test_legacy_blob_decrypts_with_v0_after_rotation(monkeypatch):
    """After rotation, legacy ciphertext (encrypted with the OLD key) should
    still decrypt because the OLD key is now installed as v0."""
    old_key = AESGCM.generate_key(bit_length=256)
    new_key = AESGCM.generate_key(bit_length=256)

    # Encrypt with the OLD key in legacy format
    nonce = os.urandom(12)
    ct = AESGCM(old_key).encrypt(nonce, b"pre-rotation value", None)
    legacy_b64 = base64.b64encode(nonce + ct).decode()

    # Simulate rotation: NEW key is active, OLD key parked in v0
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", base64.b64encode(new_key).decode())
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY_v0", base64.b64encode(old_key).decode())
    monkeypatch.setenv("ENV", "test")

    import importlib, services.encryption as enc
    importlib.reload(enc)

    pt = await enc.decrypt_credential(legacy_b64)
    assert pt == "pre-rotation value"


@pytest.mark.asyncio
async def test_versioned_v1_blob_requires_v1_key(monkeypatch):
    """A v1 ciphertext written today must still decrypt after we rotate
    keys (provided v1 key is loaded)."""
    key1 = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", base64.b64encode(key1).decode())
    monkeypatch.setenv("ENV", "test")

    import importlib, services.encryption as enc
    importlib.reload(enc)
    versioned_ct = await enc.encrypt_credential("important secret")

    # Now rotate: a NEW key becomes active, the previous key gets demoted to v0,
    # but the v1 ciphertext was written by the previous active key (which was v1).
    # In real usage we'd preserve the v1 key under CLAIMFLOW_ENCRYPTION_KEY_v0
    # AND in version slot 1 — for now this test confirms decrypt fails cleanly
    # if the originating key version isn't loaded.
    key2 = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", base64.b64encode(key2).decode())
    monkeypatch.delenv("CLAIMFLOW_ENCRYPTION_KEY_v0", raising=False)
    importlib.reload(enc)

    with pytest.raises(Exception):
        await enc.decrypt_credential(versioned_ct)
