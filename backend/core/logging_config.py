"""
ClaimFlow - Structured JSON logging configuration.
"""

import logging
import json
import os
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Standard tags injected by RequestIDLogFilter
        if hasattr(record, "request_id") and record.request_id != "-":
            log_entry["request_id"] = record.request_id
        if hasattr(record, "tenant_id"):
            log_entry["tenant_id"] = record.tenant_id
        if hasattr(record, "user_id"):
            log_entry["user_id"] = record.user_id
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def setup_logging():
    from core.request_id import RequestIDLogFilter

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    use_json = os.getenv("LOG_FORMAT", "json" if os.getenv("ENV") == "production" else "text")

    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    if use_json == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-5s [%(name)s] [%(request_id)s] %(message)s",
            defaults={"request_id": "-"},
            datefmt="%H:%M:%S",
        ))

    # Attach the request id filter to ALL records so JSON and text formatters
    # have access to it.
    rid_filter = RequestIDLogFilter()
    handler.addFilter(rid_filter)

    root.handlers = [handler]

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    # Slow query logger: any DB execution that takes longer than SLOW_QUERY_MS
    # gets logged at WARNING level. Hook into SQLAlchemy events.
    _install_slow_query_logger(int(os.getenv("SLOW_QUERY_MS", "500")))


def _install_slow_query_logger(threshold_ms: int) -> None:
    """Log queries that exceed the threshold. Called once at startup."""
    import time
    from sqlalchemy import event
    from core.database import engine

    sql_logger = logging.getLogger("noodledoc.slow_sql")

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        context._noodledoc_query_start = time.time()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        start = getattr(context, "_noodledoc_query_start", None)
        if start is None:
            return
        elapsed_ms = int((time.time() - start) * 1000)
        if elapsed_ms >= threshold_ms:
            # Truncate long statements so logs stay readable
            short = statement.replace("\n", " ").strip()[:300]
            sql_logger.warning(
                "Slow query (%dms): %s%s",
                elapsed_ms, short, "..." if len(statement) > 300 else "",
            )
