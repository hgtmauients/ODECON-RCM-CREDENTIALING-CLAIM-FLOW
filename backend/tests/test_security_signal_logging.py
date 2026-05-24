"""
Tests for structured security signal logging helper.
"""

from core.security_signal import log_security_signal


def test_log_security_signal_emits_structured_line(caplog):
    log_security_signal("rate_limit_exceeded", tenant="t1", path="/api/rcm/claims")
    line = caplog.records[-1].message
    assert "SECURITY-SIGNAL event=rate_limit_exceeded" in line
    assert "tenant=t1" in line
    assert "path=/api/rcm/claims" in line
