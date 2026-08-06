"""Thin httpx client over the Pokédex AI API — the only way this job touches the
system under evaluation (never imports the api component directly)."""

from pathlib import Path

import httpx

_IMAGE_CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


class ApiClient:
    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout)

    def search_text(
        self, query: str, mode: str = "hybrid", limit: int = 10, space: str | None = None
    ) -> dict:
        body = {"query": query, "mode": mode, "limit": limit}
        if space is not None:
            body["space"] = space
        response = self._client.post("/search/text", json=body)
        response.raise_for_status()
        return response.json()

    def search_image(self, image_path: Path, limit: int = 10) -> dict:
        content_type = _IMAGE_CONTENT_TYPES.get(
            image_path.suffix.lower(), "application/octet-stream"
        )
        with image_path.open("rb") as f:
            response = self._client.post(
                "/search/image",
                files={"image": (image_path.name, f, content_type)},
                params={"limit": limit},
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

    def compare(self, question: str, providers: list[str] | None = None) -> dict:
        body: dict = {"question": question}
        if providers is not None:
            body["providers"] = providers
        response = self._client.post("/compare", json=body)
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
