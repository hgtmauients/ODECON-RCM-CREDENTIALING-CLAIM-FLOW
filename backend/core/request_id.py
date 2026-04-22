"""
ClaimFlow - request correlation middleware.

Generates a per-request UUID (or accepts an X-Request-ID from the caller),
binds it to a contextvar so all logger calls in that request can include it,
and echoes it back in the response so clients/integrations can correlate.

Usage in app.main:
    from core.request_id import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)
"""

import logging
import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger(__name__)

# Per-request correlation id, accessible from anywhere in the call chain
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """Return the current request's correlation id, or None if outside a request."""
    return _request_id_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    HEADER = "X-Request-ID"

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(self.HEADER) or uuid.uuid4().hex
        token = _request_id_var.set(rid)
        try:
            response = await call_next(request)
            response.headers[self.HEADER] = rid
            return response
        finally:
            _request_id_var.reset(token)


class RequestIDLogFilter(logging.Filter):
    """Inject request_id into LogRecord. Add to root logger."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get() or "-"
        return True
