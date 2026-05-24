"""
Structured security telemetry helper.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def log_security_signal(event: str, **fields: Any) -> None:
    ordered = " ".join(f"{k}={fields[k]}" for k in sorted(fields.keys()))
    logger.warning("SECURITY-SIGNAL event=%s %s", event, ordered)
