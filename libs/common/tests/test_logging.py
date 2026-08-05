import json
import logging

from pokedex_common.logging import JsonFormatter, configure_logging
from pokedex_common.request_id import reset_request_id, set_request_id


def make_record(message: str, **extra: object) -> logging.LogRecord:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def test_format_produces_single_line_json_with_required_keys() -> None:
    formatter = JsonFormatter(component="api")

    line = formatter.format(make_record("hello"))

    assert "\n" not in line
    payload = json.loads(line)
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["component"] == "api"
    assert "timestamp" in payload
    assert payload["request_id"] is None


def test_format_includes_request_id_from_context() -> None:
    formatter = JsonFormatter(component="api")
    token = set_request_id("req-123")
    try:
        payload = json.loads(formatter.format(make_record("hello")))
    finally:
        reset_request_id(token)

    assert payload["request_id"] == "req-123"


def test_format_includes_extra_fields() -> None:
    formatter = JsonFormatter(component="pipeline")

    payload = json.loads(formatter.format(make_record("fetched", pokemon_id=25, attempt=2)))

    assert payload["pokemon_id"] == 25
    assert payload["attempt"] == 2


def test_format_serializes_exceptions() -> None:
    formatter = JsonFormatter(component="api")
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname=__file__,
            lineno=1,
            msg="failed",
            args=(),
            exc_info=True,
        )
        import sys

        record.exc_info = sys.exc_info()

    payload = json.loads(formatter.format(record))

    assert "ValueError: boom" in payload["exception"]


def test_configure_logging_is_idempotent() -> None:
    configure_logging(component="api", level="DEBUG")
    root = configure_logging(component="api", level="DEBUG")

    assert len(root.handlers) == 1
    assert root.level == logging.DEBUG
    assert isinstance(root.handlers[0].formatter, JsonFormatter)
