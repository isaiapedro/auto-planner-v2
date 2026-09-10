"""Privacy-safe, stdout-only operational events for the local API."""
from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Any

request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


class SafeJsonFormatter(logging.Formatter):
    """Emit allow-listed metadata only; callers must never pass Personal payloads."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = request_id.get()
        if correlation_id:
            payload["request_id"] = correlation_id
        event = getattr(record, "event", None)
        if isinstance(event, dict):
            payload["event"] = event
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def log_event(logger: logging.Logger, name: str, **event: Any) -> None:
    """Log one allow-listed event. Values must be IDs, counts, categories, or timings."""
    logger.info(name, extra={"event": event})
