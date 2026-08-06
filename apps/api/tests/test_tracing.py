"""Tracing must be a perfect no-op when Langfuse keys are absent (unit tests, CI,
and any environment that hasn't opted into observability)."""

from api.rag.tracing import Tracing


def test_disabled_without_keys() -> None:
    tracing = Tracing()

    assert tracing.enabled is False
    with tracing.chat_trace("who is pikachu?", "req-1", "v1") as (callbacks, get_trace_id):
        assert callbacks == []
        assert get_trace_id() is None


def test_disabled_with_partial_keys() -> None:
    assert Tracing(public_key="pk-only").enabled is False
    assert Tracing(secret_key="sk-only").enabled is False
