import json

import httpx
import respx

from evals.client import ApiClient

BASE = "http://api.test"


def write_png(path) -> None:
    # Smallest valid PNG signature is enough — the api is mocked, nothing decodes it.
    path.write_bytes(b"\x89PNG\r\n\x1a\n")


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
def test_search_image_uploads_the_file_with_the_right_content_type(tmp_path) -> None:
    image_path = tmp_path / "1-default.png"
    write_png(image_path)
    route = respx.post(f"{BASE}/search/image").respond(
        json={"mode": "image", "results": [{"pokemon_id": 1, "score": 1.0}]}
    )

    with ApiClient(BASE) as client:
        result = client.search_image(image_path, limit=5)

    assert result["results"][0]["pokemon_id"] == 1
    sent = route.calls[0].request
    assert httpx.URL(sent.url).params["limit"] == "5"
    assert b'filename="1-default.png"' in sent.content
    assert b"Content-Type: image/png" in sent.content


@respx.mock
def test_search_image_defaults_unknown_extensions_to_octet_stream(tmp_path) -> None:
    image_path = tmp_path / "1-default.gif"
    write_png(image_path)
    route = respx.post(f"{BASE}/search/image").respond(json={"mode": "image", "results": []})

    with ApiClient(BASE) as client:
        client.search_image(image_path)

    assert b"Content-Type: application/octet-stream" in route.calls[0].request.content


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
