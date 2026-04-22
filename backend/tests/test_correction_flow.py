"""
Tests for the FG9 corrected/replacement claim flow.

These cover the pieces that don't need a database — schema validation on
the request body and the EDI-builder's CLM05 frequency code emission. The
end-to-end "correct an existing claim" path is exercised by the existing
integration test suite once the endpoint is live.
"""

import pytest
from pydantic import ValidationError

from api.rcm.claims import CorrectionRequest


def test_correction_request_defaults_to_replacement():
    body = CorrectionRequest()
    assert body.kind == "replacement"
    assert body.reason is None


def test_correction_request_accepts_void():
    body = CorrectionRequest(kind="void", reason="Wrong patient")
    assert body.kind == "void"
    assert body.reason == "Wrong patient"


@pytest.mark.parametrize("bad", ["delete", "amend", "", "REPLACEMENT"])
def test_correction_request_rejects_unknown_kind(bad):
    with pytest.raises(ValidationError):
        CorrectionRequest(kind=bad)


def test_correction_request_caps_reason_length():
    too_long = "x" * 2001
    with pytest.raises(ValidationError):
        CorrectionRequest(reason=too_long)


def test_correction_request_extras_ignored():
    body = CorrectionRequest(kind="replacement", reason=None, extra_field="ignored")  # type: ignore[arg-type]
    assert not hasattr(body, "extra_field")


def test_837_clm_segment_includes_frequency_code():
    """Smoke check: the CLM segment template uses claim.claim_frequency_code."""
    import inspect
    import services.edi_processor as ep

    src = inspect.getsource(ep.EDIProcessor._build_837_file)
    # CLM05-3 must be parameterized off claim.claim_frequency_code with a
    # safe "1" default.
    assert "claim.claim_frequency_code or '1'" in src or 'claim.claim_frequency_code or "1"' in src


def test_837_emits_ref_f8_for_replacement_or_void():
    """Smoke check: the F8 reference branch fires for codes 7 and 8."""
    import inspect
    import services.edi_processor as ep

    src = inspect.getsource(ep.EDIProcessor._build_837_file)
    assert 'REF*F8*' in src
    # Branch must include both 7 and 8.
    assert '("7", "8")' in src or '"7", "8"' in src
