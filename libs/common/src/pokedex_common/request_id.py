"""Request-id propagation via contextvars.

The id is generated (or accepted from the caller) at the process edge — HTTP middleware
or CLI entrypoint — and read by the JSON log formatter for every event in that context.
"""

import uuid
from contextvars import ContextVar, Token

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def set_request_id(value: str) -> Token[str | None]:
    return _request_id.set(value)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def get_request_id() -> str | None:
    return _request_id.get()
