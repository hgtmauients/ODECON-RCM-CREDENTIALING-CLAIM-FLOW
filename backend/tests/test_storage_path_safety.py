"""
Tests for core.storage path sanitization + traversal protection.

These tests codify the contract that prevents the v10 NEW-C2 finding
(path traversal in document upload). Each "../" or absolute-path attempt
must raise StoragePathError before any byte is written.
"""

import os
import importlib

import pytest


@pytest.fixture
def storage_module(tmp_path, monkeypatch):
    """Force the storage module to use a fresh temp dir as its root."""
    monkeypatch.setenv("EDI_STORAGE_PATH", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    import core.storage as s
    importlib.reload(s)
    return s


@pytest.mark.parametrize("bad", ["..", ".", "", "a/b", "a\\b", "a\x00b", "../x", "..\\x"])
def test_sanitize_component_rejects_unsafe_inputs(storage_module, bad):
    with pytest.raises(storage_module.StoragePathError):
        storage_module.sanitize_component(bad)


@pytest.mark.parametrize("good", ["abc", "abc.pdf", "FILE_123", "20260101_120000_x.pdf", "a-b_c.PDF"])
def test_sanitize_component_accepts_safe_inputs(storage_module, good):
    assert storage_module.sanitize_component(good) == good


def test_safe_filename_strips_path_separators(storage_module):
    out = storage_module.safe_filename("../../etc/passwd", fallback="x.bin")
    assert "/" not in out and ".." not in out and "\\" not in out


def test_safe_filename_replaces_disallowed_chars(storage_module):
    out = storage_module.safe_filename("My Doc<v1>!.PDF", fallback="x.bin")
    assert all(c.isalnum() or c in "._-" for c in out)


def test_safe_filename_falls_back_when_empty(storage_module):
    out = storage_module.safe_filename("", fallback="alt.bin")
    assert out == "alt.bin"


def test_build_relative_path_rejects_traversal(storage_module):
    with pytest.raises(storage_module.StoragePathError):
        storage_module.build_relative_path("a", "..", "b")


def test_build_relative_path_joins_clean_components(storage_module):
    assert storage_module.build_relative_path("providers", "PROV_1", "doc.pdf") == "providers/PROV_1/doc.pdf"


@pytest.mark.asyncio
async def test_local_write_rejects_traversal_in_components(storage_module, tmp_path):
    # The path crafted here would historically resolve to ../escape via the OS;
    # the sanitizer must block it before any FS interaction.
    with pytest.raises(storage_module.StoragePathError):
        await storage_module.storage.write(
            "providers/../../escape/file.pdf",
            b"hello",
            tenant_id="tenant-uuid-1",
        )


@pytest.mark.asyncio
async def test_local_write_writes_inside_tenant_root(storage_module, tmp_path):
    out_path = await storage_module.storage.write(
        "providers/PROV_1/doc.pdf",
        b"hello",
        tenant_id="tenant-uuid-1",
    )
    expected_root = (tmp_path / "tenant-uuid-1").resolve()
    assert os.path.realpath(out_path).startswith(str(expected_root))


@pytest.mark.asyncio
async def test_local_write_rejects_absolute_tenant_id(storage_module):
    with pytest.raises(storage_module.StoragePathError):
        await storage_module.storage.write(
            "doc.pdf",
            b"hello",
            tenant_id="/etc",
        )


@pytest.mark.asyncio
async def test_local_read_refuses_outside_root(storage_module, tmp_path):
    # Plant a file outside the storage root and confirm read refuses it.
    outsider = tmp_path.parent / "outsider.txt"
    outsider.write_bytes(b"secret")
    with pytest.raises(storage_module.StoragePathError):
        await storage_module.storage.read(str(outsider))
