"""
Tests for the Argon2 password helper used by the User table.
"""

import pytest

from core.password import hash_password, verify_password, needs_rehash


def test_hash_round_trip():
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2")
    assert verify_password("correct horse battery staple", h) is True


def test_wrong_password_fails():
    h = hash_password("right")
    assert verify_password("wrong", h) is False


def test_empty_hash_returns_false():
    assert verify_password("anything", "") is False
    assert verify_password("anything", None) is False  # type: ignore[arg-type]


def test_garbage_hash_returns_false():
    assert verify_password("x", "not-an-argon2-hash") is False


def test_needs_rehash_on_garbage_returns_false_safely():
    assert needs_rehash("garbage") is False
