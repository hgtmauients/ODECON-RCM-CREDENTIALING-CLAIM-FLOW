import pytest
from fastapi import HTTPException

import api.dev_login as dev_login

pytestmark = pytest.mark.security


def test_login_throttle_blocks_after_limit(monkeypatch):
    monkeypatch.setattr(dev_login, "LOGIN_ATTEMPT_LIMIT", 3)
    monkeypatch.setattr(dev_login, "LOGIN_ATTEMPT_WINDOW_SECONDS", 900)
    dev_login._failed_login_attempts.clear()

    for _ in range(3):
        dev_login._record_failed_login(email="user@example.com", client_ip="1.2.3.4")

    with pytest.raises(HTTPException) as exc:
        dev_login._enforce_login_throttle(email="user@example.com", client_ip="1.2.3.4")
    assert exc.value.status_code == 429


def test_login_throttle_clears_after_success(monkeypatch):
    monkeypatch.setattr(dev_login, "LOGIN_ATTEMPT_LIMIT", 3)
    dev_login._failed_login_attempts.clear()
    dev_login._record_failed_login(email="user@example.com", client_ip="1.2.3.4")
    dev_login._clear_failed_login(email="user@example.com", client_ip="1.2.3.4")

    # Should not raise once attempts are cleared.
    dev_login._enforce_login_throttle(email="user@example.com", client_ip="1.2.3.4")
