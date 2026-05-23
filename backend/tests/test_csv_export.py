"""
Tests for the CSV streaming helper.
"""

from datetime import datetime, timezone

import pytest

from core.csv_export import (
    csv_response,
    _safe_filename,
    _serialize_value,
)


def test_safe_filename_strips_unsafe_chars():
    assert _safe_filename("../etc/passwd") == "etc_passwd"
    assert _safe_filename("good_name.csv") == "good_name.csv"
    assert _safe_filename("") == "export.csv"


def test_serialize_value_handles_common_types():
    assert _serialize_value(None) == ""
    assert _serialize_value(True) == "true"
    assert _serialize_value(False) == "false"
    assert _serialize_value(42) == "42"
    assert _serialize_value(3.14) == "3.14"
    assert _serialize_value("plain") == "plain"
    dt = datetime(2026, 4, 22, 0, 0, tzinfo=timezone.utc)
    assert _serialize_value(dt) == "2026-04-22T00:00:00+00:00"


def test_serialize_value_neutralizes_spreadsheet_formula_cells():
    assert _serialize_value("=2+2") == "'=2+2"
    assert _serialize_value("+SUM(A1:A2)") == "'+SUM(A1:A2)"
    assert _serialize_value("-10+20") == "'-10+20"
    assert _serialize_value("@evil") == "'@evil"
    # Leading spaces are preserved while still neutralizing formula execution.
    assert _serialize_value("   =cmd|' /C calc'!A0") == "'   =cmd|' /C calc'!A0"
    assert _serialize_value("safe-text") == "safe-text"


async def _consume(response) -> str:
    """Drain a StreamingResponse to a string for assertions."""
    chunks = []
    body_iterator = response.body_iterator
    async for chunk in body_iterator:
        chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
    return b"".join(chunks).decode("utf-8")


@pytest.mark.asyncio
async def test_csv_response_writes_header_and_rows():
    rows = [
        {"id": 1, "name": "Alpha", "amount": 10.5, "active": True},
        {"id": 2, "name": "Beta", "amount": None, "active": False},
    ]
    resp = csv_response(filename="test.csv", rows=rows, fieldnames=["id", "name", "amount", "active"])
    body = await _consume(resp)
    lines = [l for l in body.splitlines() if l]
    assert lines[0] == "id,name,amount,active"
    assert lines[1] == "1,Alpha,10.5,true"
    assert lines[2] == "2,Beta,,false"
    assert resp.headers["Content-Disposition"].endswith('filename="test.csv"')
    assert "no-store" in resp.headers["Cache-Control"]


@pytest.mark.asyncio
async def test_csv_response_with_row_to_dict():
    class _Row:
        def __init__(self, x: int, y: str) -> None:
            self.x, self.y = x, y

    rows = [_Row(1, "a"), _Row(2, "b")]
    resp = csv_response(
        filename="custom.csv",
        rows=rows,
        fieldnames=["x", "y"],
        row_to_dict=lambda r: {"x": r.x, "y": r.y},
    )
    body = await _consume(resp)
    assert "x,y\r\n1,a\r\n2,b\r\n" in body or "x,y\n1,a\n2,b\n" in body


@pytest.mark.asyncio
async def test_csv_response_extra_keys_ignored():
    rows = [{"a": 1, "b": 2, "extra": "drop"}]
    resp = csv_response(filename="t.csv", rows=rows, fieldnames=["a", "b"])
    body = await _consume(resp)
    assert "extra" not in body
