"""
Tests for structured security signal logging helper.
"""

import json
import logging

from core.logging_config import JSONFormatter
from core.security_signal import log_security_signal


def test_log_security_signal_emits_structured_line(caplog):
    log_security_signal("rate_limit_exceeded", tenant="t1", path="/api/rcm/claims")
    line = caplog.records[-1].message
    assert "SECURITY-SIGNAL event=rate_limit_exceeded" in line
    assert "tenant=t1" in line
    assert "path=/api/rcm/claims" in line
    assert getattr(caplog.records[-1], "security_event") == "rate_limit_exceeded"
    assert getattr(caplog.records[-1], "security_fields") == {
        "tenant": "t1",
        "path": "/api/rcm/claims",
    }


def test_json_formatter_includes_security_event_fields():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="core.security_signal",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="SECURITY-SIGNAL event=%s %s",
        args=("tenant_override_denied", "tenant_id=t1"),
        exc_info=None,
    )
    record.security_event = "tenant_override_denied"
    record.security_fields = {"tenant_id": "t1", "requested_tenant_id": "t2"}

    out = formatter.format(record)
    payload = json.loads(out)
    assert payload["security_event"] == "tenant_override_denied"
    assert payload["security_fields"]["tenant_id"] == "t1"
    assert payload["security_fields"]["requested_tenant_id"] == "t2"
