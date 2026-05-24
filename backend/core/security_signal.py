"""
Structured security telemetry helper.
"""

from __future__ import annotations

import logging
import json
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)
SCHEMA_VERSION = 1


def log_security_signal(event: str, **fields: Any) -> None:
    normalized_fields = {
        str(k): _normalize_value(v)
        for k, v in fields.items()
    }
    normalized_fields["schema_version"] = SCHEMA_VERSION
    normalized_fields["env"] = os.getenv("ENV", "development")
    normalized_fields["emitted_at_utc"] = datetime.now(timezone.utc).isoformat()
    ordered = " ".join(f"{k}={normalized_fields[k]}" for k in sorted(normalized_fields.keys()))
    logger.warning(
        "SECURITY-SIGNAL event=%s %s",
        event,
        ordered,
        extra={
            "security_event": event,
            "security_fields": normalized_fields,
        },
    )


def _normalize_value(value: Any) -> Any:
    """Keep security field values JSON-serializable for structured sinks."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)
