"""
CSV streaming helpers for the export.csv endpoints.

Why streaming: even mid-size tenants can have tens of thousands of claims,
and we want the response to start flushing bytes immediately rather than
buffering the whole file in memory before the first byte hits the wire.

Usage:
    rows = (await db.execute(query)).scalars().all()
    return csv_response(
        filename="claims.csv",
        rows=rows,
        fieldnames=["id", "claim_number", "state", ...],
        row_to_dict=lambda c: {"id": c.id, "claim_number": c.claim_number, ...},
    )
"""

import csv
import io
import re
from datetime import datetime
from typing import Any, Callable, Iterable, List, Optional, Sequence

from fastapi.responses import StreamingResponse


def _safe_filename(name: str) -> str:
    """Strip any character not in the conservative filename allowlist."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._-")
    return cleaned or "export.csv"


def _serialize_value(value: Any) -> str:
    """Convert a Python value into a CSV-safe string.

    - datetime → ISO 8601 with 'Z'
    - None     → empty string
    - bool     → 'true' / 'false'
    - dict / list → repr (caller usually shouldn't include these)
    - everything else → str()
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return repr(value)
    return str(value)


def csv_response(
    *,
    filename: str,
    rows: Iterable[Any],
    fieldnames: Sequence[str],
    row_to_dict: Optional[Callable[[Any], dict]] = None,
) -> StreamingResponse:
    """Stream `rows` to the client as CSV.

    `rows` may be ORM objects, dicts, or anything `row_to_dict` can convert
    into a {fieldname: value} mapping. If `row_to_dict` is not supplied, the
    helper assumes each row is already a dict.
    """
    safe_name = _safe_filename(filename)

    def _generate() -> Iterable[bytes]:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        yield buf.getvalue().encode("utf-8")
        buf.seek(0); buf.truncate(0)

        for row in rows:
            data = row_to_dict(row) if row_to_dict else row
            writer.writerow({k: _serialize_value(data.get(k)) for k in fieldnames})
            yield buf.getvalue().encode("utf-8")
            buf.seek(0); buf.truncate(0)

    return StreamingResponse(
        _generate(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            # Don't let intermediaries cache PHI exports
            "Cache-Control": "no-store, must-revalidate",
            "Pragma": "no-cache",
        },
    )
