"""
Schema tests for the self-service password change endpoint.
"""

import pytest
from pydantic import ValidationError

from api.dev_login import ChangePasswordRequest


def test_valid_payload():
    body = ChangePasswordRequest(current_password="old-pass-123", new_password="brand-new-1234")
    assert body.current_password == "old-pass-123"
    assert body.new_password == "brand-new-1234"


def test_new_password_minimum_length():
    with pytest.raises(ValidationError):
        ChangePasswordRequest(current_password="ok", new_password="short1")


def test_current_password_can_be_anything_nonempty():
    """Current password isn\'t length-checked here — verify_password gates that."""
    body = ChangePasswordRequest(current_password="x", new_password="brand-new-1234")
    assert body.current_password == "x"


def test_extras_ignored():
    body = ChangePasswordRequest(
        current_password="old-pass-123",
        new_password="brand-new-1234",
        force_logout=True,  # type: ignore[arg-type]
    )
    assert not hasattr(body, "force_logout")
