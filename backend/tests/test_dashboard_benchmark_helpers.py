from models.claims import ClaimState
from api.dashboard import _coerce_state_key, _delta_pct, _median


def test_delta_pct_handles_zero_previous():
    assert _delta_pct(12.0, 0.0) is None


def test_delta_pct_positive_and_negative_values():
    assert _delta_pct(120.0, 100.0) == 20.0
    assert _delta_pct(80.0, 100.0) == -20.0


def test_coerce_state_key_uses_enum_value():
    assert _coerce_state_key(ClaimState.DRAFT) == "draft"
    assert _coerce_state_key("submitted") == "submitted"


def test_median_for_even_and_odd_lists():
    assert _median([3.0, 1.0, 2.0]) == 2.0
    assert _median([4.0, 1.0, 2.0, 3.0]) == 2.5
