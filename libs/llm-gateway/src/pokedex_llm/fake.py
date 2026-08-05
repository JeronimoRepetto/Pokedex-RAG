"""Deterministic offline gateway for tests: scripted responses and error injection."""

from collections.abc import Iterator

from pokedex_llm.gateway import GenerationRequest, GenerationResult, Usage


class FakeLLM:
    """Yields queued items in order; an Exception item is raised instead of returned.

    With an empty queue it falls back to `default_response`, so graph tests that only
    care about the flow don't need to script every call.
    """

    def __init__(
        self,
        script: list[str | Exception] | None = None,
        default_response: str = "fake answer",
        provider: str = "fake",
        model: str = "fake-model",
    ) -> None:
        self._script = list(script or [])
        self._default = default_response
        self._provider = provider
        self._model = model
        self.requests: list[GenerationRequest] = []

    @property
    def provider_name(self) -> str:
        return self._provider

    @property
    def model_name(self) -> str:
        return self._model

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        item = self._script.pop(0) if self._script else self._default
        if isinstance(item, Exception):
            raise item
        prompt_tokens = sum(len(m.content.split()) for m in request.messages)
        return GenerationResult(
            text=item,
            usage=Usage(prompt_tokens=prompt_tokens, output_tokens=len(item.split())),
            model=self._model,
            provider=self._provider,
        )

    def stream(self, request: GenerationRequest) -> Iterator[str]:
        text = self.generate(request).text
        midpoint = max(1, len(text) // 2)
        yield text[:midpoint]
        if text[midpoint:]:
            yield text[midpoint:]
