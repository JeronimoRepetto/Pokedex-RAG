import json

import httpx
import respx

from evals.client import ApiClient

BASE = "http://api.test"


@respx.mock
def test_search_text_posts_the_request_body_and_returns_json() -> None:
    route = respx.post(f"{BASE}/search/text").respond(
        json={"mode": "hybrid", "results": [{"pokemon_id": 1, "score": 0.9}]}
    )

    with ApiClient(BASE) as client:
        result = client.search_text("what type is bulbasaur", mode="hybrid", limit=5)

    assert result["results"][0]["pokemon_id"] == 1
    sent = route.calls[0].request
    assert httpx.URL(sent.url).path == "/search/text"


@respx.mock
def test_chat_omits_provider_when_not_given() -> None:
    route = respx.post(f"{BASE}/chat").respond(json={"status": "answered"})

    with ApiClient(BASE) as client:
        client.chat("what type is squirtle?")

    assert "provider" not in json.loads(route.calls[0].request.content)


@respx.mock
def test_chat_includes_provider_override_when_given() -> None:
    route = respx.post(f"{BASE}/chat").respond(json={"status": "answered"})

    with ApiClient(BASE) as client:
        client.chat("what type is squirtle?", provider="ai-studio-gemini")

    assert json.loads(route.calls[0].request.content)["provider"] == "ai-studio-gemini"


@respx.mock
def test_raises_on_http_error() -> None:
    respx.post(f"{BASE}/search/text").respond(status_code=500)

    with ApiClient(BASE) as client:
        try:
            client.search_text("x")
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 500
        else:
            raise AssertionError("expected HTTPStatusError")
