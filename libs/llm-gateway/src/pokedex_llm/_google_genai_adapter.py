"""Shared retry/mapping logic for google-genai-backed adapters (Vertex, AI Studio).

The two adapters differ only in how the `genai.Client` is constructed (ADC + project/
location vs. an API key) — everything downstream of an already-constructed client is
identical, so it lives here once instead of twice.
"""

import logging
import time
from collections.abc import Callable, Iterator

from pokedex_llm.gateway import (
    GenerationRequest,
    GenerationResult,
    PermanentProviderError,
    TransientProviderError,
    Usage,
)

logger = logging.getLogger(__name__)

TRANSIENT_STATUS_CODES = {429, 500, 502, 503, 504}


class GoogleGenAiAdapter:
    def __init__(
        self,
        *,
        client: object,
        model: str,
        provider_name: str,
        max_attempts: int = 3,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._client = client
        self._model = model
        self._provider_name = provider_name
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._sleep = sleep

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, request: GenerationRequest) -> GenerationResult:
        response = self._call(request, stream=False)
        text = response.text or ""
        usage = getattr(response, "usage_metadata", None)
        thoughts = getattr(usage, "thoughts_token_count", 0) or 0
        visible = getattr(usage, "candidates_token_count", 0) or 0
        return GenerationResult(
            text=text,
            usage=Usage(
                prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                # Thinking tokens are billed output too — cost tracking must see them.
                output_tokens=visible + thoughts,
            ),
            model=self._model,
            provider=self.provider_name,
            metadata={"thoughts_tokens": thoughts, "visible_tokens": visible},
        )

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        for chunk in self._call(request, stream=True):
            if chunk.text:
                yield chunk.text

    def _call(self, request: GenerationRequest, *, stream: bool):
        from google.genai import errors, types

        system_parts = [m.content for m in request.messages if m.role == "system"]
        contents = [
            types.Content(
                role="user" if message.role == "user" else "model",
                parts=[types.Part.from_text(text=message.content)],
            )
            for message in request.messages
            if message.role != "system"
        ]
        config = types.GenerateContentConfig(
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            system_instruction="\n\n".join(system_parts) if system_parts else None,
            response_mime_type=request.response_mime_type,
        )

        method = (
            self._client.models.generate_content_stream
            if stream
            else self._client.models.generate_content
        )
        last_error = "unknown"
        for attempt in range(1, self._max_attempts + 1):
            try:
                return method(model=self._model, contents=contents, config=config)
            except errors.APIError as exc:
                if exc.code not in TRANSIENT_STATUS_CODES:
                    raise PermanentProviderError(
                        f"{self.provider_name}/{self._model}: {exc.code} {exc.message}"
                    ) from exc
                last_error = f"HTTP {exc.code}"
            if attempt < self._max_attempts:
                delay = self._backoff_base * 2 ** (attempt - 1)
                logger.warning(
                    "llm retry",
                    extra={
                        "provider": self.provider_name,
                        "model": self._model,
                        "attempt": attempt,
                        "reason": last_error,
                        "backoff_seconds": delay,
                    },
                )
                self._sleep(delay)
        raise TransientProviderError(
            f"{self.provider_name}/{self._model}: gave up after {self._max_attempts} "
            f"attempts; last error: {last_error}"
        )
