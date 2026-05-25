from services.alert_hooks import _should_emit_breach


def test_should_emit_breach_only_on_non_breach_to_breach_transition():
    assert _should_emit_breach(None, "breach") is True
    assert _should_emit_breach("ok", "breach") is True
    assert _should_emit_breach("warning", "breach") is True

    assert _should_emit_breach("breach", "breach") is False
    assert _should_emit_breach("breach", "warning") is False
    assert _should_emit_breach("ok", "ok") is False
