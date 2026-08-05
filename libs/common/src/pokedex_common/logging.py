"""Structured JSON logging: one line per event.

Every record carries timestamp, level, message, component and the request_id from the
current context. Extra fields passed via ``logger.info(..., extra={...})`` are included
as top-level keys as long as they don't collide with the reserved ones.
"""

import json
import logging
import sys
from datetime import UTC, datetime

from pokedex_common.request_id import get_request_id

_RECORD_BUILTIN_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


class JsonFormatter(logging.Formatter):
    def __init__(self, component: str) -> None:
        super().__init__()
        self.component = component

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "component": self.component,
            "request_id": get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _RECORD_BUILTIN_ATTRS and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(component: str, level: str = "INFO") -> logging.Logger:
    """Configure the root logger for JSON output to stdout. Idempotent."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(component))
    root.addHandler(handler)
    return root
