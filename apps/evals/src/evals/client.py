"""Thin httpx client over the Pokédex AI API — the only way this job touches the
system under evaluation (never imports the api component directly)."""

import httpx


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def search_text(self, query: str, mode: str = "hybrid", limit: int = 10) -> dict:
        response = self._client.post(
            "/search/text", json={"query": query, "mode": mode, "limit": limit}
        )
        response.raise_for_status()
        return response.json()

    def chat(self, question: str, provider: str | None = None) -> dict:
        body = {"question": question}
        if provider is not None:
            body["provider"] = provider
        response = self._client.post("/chat", json=body)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
