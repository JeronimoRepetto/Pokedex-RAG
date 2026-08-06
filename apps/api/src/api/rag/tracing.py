"""Langfuse tracing wrapper — optional by configuration, invisible when disabled.

The SDK is OTel-based: we open a root span per chat, the LangChain CallbackHandler
nests one span per graph node under it, and the trace id links the rag_answers row to
the Langfuse UI. flush() after each ask keeps short-lived processes (scripts, tests)
from losing buffered events; the volume here makes that cost irrelevant.

Verified against langfuse 4.14.x, whose span API is `start_as_current_observation`
(the v3 `start_as_current_span` no longer exists) — hence the exact-ish pin in
pyproject.
"""

import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class Tracing:
    """Disabled unless both Langfuse keys are configured."""

    def __init__(self, *, public_key: str = "", secret_key: str = "", host: str = "") -> None:
        self.enabled = bool(public_key and secret_key)
        self._client = None
        self._handler = None
        if not self.enabled:
            return
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        self._handler = CallbackHandler()

    @contextmanager
    def chat_trace(self, question: str, request_id: str, prompt_version: str):
        """Yields (callbacks, get_trace_id) — empty/no-op when tracing is disabled."""
        if not self.enabled:
            yield [], lambda: None
            return
        with self._client.start_as_current_observation(name="pokedex-chat", as_type="span") as span:
            span.update(
                input={"question": question},
                metadata={"request_id": request_id, "prompt_version": prompt_version},
            )
            span.set_trace_io(input={"question": question})
            yield [self._handler], self._client.get_current_trace_id
        self._client.flush()
