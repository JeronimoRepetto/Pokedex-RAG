"""Google AI Studio (Gemini Developer API) adapter — same google-genai SDK as Vertex,
different auth path (API key instead of ADC/project/location). Verified live 2026-08-06
against gemini-3.5-flash-lite (devlog 0024, cost-log)."""

import time
from collections.abc import Callable

from pokedex_llm._google_genai_adapter import GoogleGenAiAdapter


class AiStudioGeminiAdapter(GoogleGenAiAdapter):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_attempts: int = 3,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        client: object | None = None,
    ) -> None:
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        super().__init__(
            client=client,
            model=model,
            provider_name="ai-studio-gemini",
            max_attempts=max_attempts,
            backoff_base_seconds=backoff_base_seconds,
            sleep=sleep,
        )
