"""Asserts the JSON log formatter never emits sensitive field values (spec §63)."""

from __future__ import annotations

import json
import logging

from app.platform.logging import JsonFormatter


def _format(record: logging.LogRecord) -> dict:
    return json.loads(JsonFormatter().format(record))


def test_sensitive_extra_fields_are_redacted() -> None:
    logger = logging.getLogger("test.sensitive")
    record = logger.makeRecord(
        name="test.sensitive",
        level=logging.INFO,
        fn=__file__,
        lno=0,
        msg="processing conversation",
        args=(),
        exc_info=None,
        extra={
            "transcript": "the actual spoken transcript content",
            "prompt": "the actual LLM prompt",
            "password": "hunter2",
            "conversation_id": "abc-123",
        },
    )
    payload = _format(record)

    assert payload["transcript"] == "[REDACTED]"
    assert payload["prompt"] == "[REDACTED]"
    assert payload["password"] == "[REDACTED]"
    # non-sensitive fields pass through untouched
    assert payload["conversation_id"] == "abc-123"


def test_message_and_metadata_present() -> None:
    logger = logging.getLogger("test.basic")
    record = logger.makeRecord(
        name="test.basic",
        level=logging.INFO,
        fn=__file__,
        lno=0,
        msg="hello",
        args=(),
        exc_info=None,
    )
    payload = _format(record)
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert "timestamp" in payload
