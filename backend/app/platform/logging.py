"""Structured JSON logging.

Deliberately stdlib-only (no `structlog`) for Phase 0 — a small JSON
formatter plus a request-id contextvar covers everything we need.

Hard rule (spec §63): never log transcript content, audio bytes/paths beyond
opaque IDs, LLM prompts/completions, or secrets. Call sites must not pass
these as log fields. `JsonFormatter` also defensively redacts a fixed list of
sensitive field names if they ever slip through.
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

_REQUEST_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id", default=None
)

# Field names that must never appear in log output, even if a caller
# accidentally passes them via `extra=`.
_SENSITIVE_KEYS = {
    "transcript",
    "transcript_text",
    "audio",
    "audio_bytes",
    "prompt",
    "llm_prompt",
    "llm_completion",
    "password",
    "secret",
    "token",
    "api_key",
    "authorization",
}


def set_request_id(request_id: str | None) -> None:
    """Bind the current request id to the logging contextvar."""
    _REQUEST_ID.set(request_id)


def get_request_id() -> str | None:
    """Return the request id bound to the current context, if any."""
    return _REQUEST_ID.get()


class JsonFormatter(logging.Formatter):
    """Renders each LogRecord as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id

        for key, value in record.__dict__.items():
            if key in (
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "taskName",
            ):
                continue
            if key.lower() in _SENSITIVE_KEYS:
                payload[key] = "[REDACTED]"
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Configure the root logger. Call once at process startup."""
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler(stream=sys.stdout)
    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    root.handlers.clear()
    root.addHandler(handler)
