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
async def test_versioned_v1_blob_decrypts_after_rotation_to_v2(monkeypatch):
    """v1 ciphertext written today MUST still decrypt after rotating to v2,
    as long as the v1 key is parked in CLAIMFLOW_ENCRYPTION_KEY_v1.

    This codifies the rotation contract: bump CLAIMFLOW_ENCRYPTION_KEY_VERSION,
    install the new key in CLAIMFLOW_ENCRYPTION_KEY, move the OLD key to its
    versioned slot. New writes use the new active version; old reads still work.
    """
    key1 = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", base64.b64encode(key1).decode())
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY_VERSION", "1")
    monkeypatch.setenv("ENV", "test")

    import importlib, services.encryption as enc
    importlib.reload(enc)
    versioned_ct_v1 = await enc.encrypt_credential("v1 secret")
    assert (await enc.decrypt_credential(versioned_ct_v1)) == "v1 secret"

    # Rotate to v2: new key is active, OLD key parked in v1 slot.
    key2 = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", base64.b64encode(key2).decode())
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY_VERSION", "2")
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY_v1", base64.b64encode(key1).decode())
    importlib.reload(enc)

    # OLD ciphertext still decrypts via the v1 slot.
    assert (await enc.decrypt_credential(versioned_ct_v1)) == "v1 secret"

    # New writes use v2.
    versioned_ct_v2 = await enc.encrypt_credential("v2 secret")
    raw = base64.b64decode(versioned_ct_v2)
    assert raw[0:1] == b"v" and raw[1] == 2
    assert (await enc.decrypt_credential(versioned_ct_v2)) == "v2 secret"


@pytest.mark.asyncio
async def test_reencrypt_with_active_key_migrates_version(monkeypatch):
    """reencrypt_with_active_key reads a v1 blob and writes a v2 blob."""
    key1 = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", base64.b64encode(key1).decode())
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY_VERSION", "1")
    monkeypatch.setenv("ENV", "test")

    import importlib, services.encryption as enc
    importlib.reload(enc)
    blob_v1 = await enc.encrypt_credential("rotateme")

    key2 = AESGCM.generate_key(bit_length=256)
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY", base64.b64encode(key2).decode())
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY_VERSION", "2")
    monkeypatch.setenv("CLAIMFLOW_ENCRYPTION_KEY_v1", base64.b64encode(key1).decode())
    importlib.reload(enc)

    blob_v2 = await enc.reencrypt_with_active_key(blob_v1)
    raw = base64.b64decode(blob_v2)
    assert raw[1] == 2  # now under v2
    assert (await enc.decrypt_credential(blob_v2)) == "rotateme"
