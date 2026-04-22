"""
Tests for the X12 277CA STC01 → claim state mapping.
"""

import pytest

from services.edi_processor import _map_stc_to_state
from models.claims import ClaimState


@pytest.mark.parametrize("code", ["A1", "A2", "A3", "A4", "A6", "F"])
def test_acceptance_codes_map_to_accepted(code):
    assert _map_stc_to_state(code) == ClaimState.ACCEPTED


@pytest.mark.parametrize("code", ["R0", "R1", "R5", "R29", "E"])
def test_rejection_codes_map_to_rejected(code):
    assert _map_stc_to_state(code) == ClaimState.REJECTED


@pytest.mark.parametrize("code", ["WQ", "P", "P0", "P1"])
def test_pending_codes_leave_state_alone(code):
    assert _map_stc_to_state(code) is None


@pytest.mark.parametrize("code", ["", None, "ZZ", "9", "X4"])
def test_unknown_or_empty_returns_none(code):
    assert _map_stc_to_state(code) is None


def test_lowercase_input_normalized():
    assert _map_stc_to_state("a1") == ClaimState.ACCEPTED
    assert _map_stc_to_state(" wq ") is None
