import httpx
import pytest
import respx

from pipeline.pokeapi import PokeApiClient, PokeApiError, PokeApiNotFound

BASE = "https://pokeapi.test/api/v2"


def make_client(**overrides) -> tuple[PokeApiClient, list[float]]:
    sleeps: list[float] = []
    clock = {"now": 0.0}

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock["now"] += seconds

    def fake_monotonic() -> float:
        clock["now"] += 0.001  # a millisecond passes per observation
        return clock["now"]

    defaults = {
        "timeout_seconds": 30.0,
        "rate_limit_per_sec": 3.0,
        "max_attempts": 4,
        "backoff_base_seconds": 1.0,
        "sleep": fake_sleep,
        "monotonic": fake_monotonic,
    }
    defaults.update(overrides)
    return PokeApiClient(BASE, **defaults), sleeps


@respx.mock
def test_returns_payload_and_final_url() -> None:
    respx.get(f"{BASE}/pokemon/25").respond(json={"name": "pikachu"})
    client, _ = make_client()

    payload, url = client.get_json("/pokemon/25")

    assert payload == {"name": "pikachu"}
    assert url == f"{BASE}/pokemon/25"


@respx.mock
def test_throttles_consecutive_requests() -> None:
    respx.get(f"{BASE}/pokemon/1").respond(json={})
    respx.get(f"{BASE}/pokemon/2").respond(json={})
    client, sleeps = make_client(rate_limit_per_sec=2.0)

    client.get_json("/pokemon/1")
    client.get_json("/pokemon/2")

    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.5, abs=0.05)


@respx.mock
def test_retries_on_429_with_exponential_backoff() -> None:
    route = respx.get(f"{BASE}/pokemon/25")
    route.side_effect = [
        httpx.Response(429),
        httpx.Response(429),
        httpx.Response(200, json={"name": "pikachu"}),
    ]
    client, sleeps = make_client()

    payload, _ = client.get_json("/pokemon/25")

    assert payload == {"name": "pikachu"}
    backoffs = [s for s in sleeps if s >= 1.0]
    assert backoffs == [1.0, 2.0]


@respx.mock
def test_retries_on_500_and_transport_errors() -> None:
    route = respx.get(f"{BASE}/pokemon/25")
    route.side_effect = [
        httpx.Response(503),
        httpx.ConnectError("boom"),
        httpx.Response(200, json={"ok": True}),
    ]
    client, _ = make_client()

    payload, _ = client.get_json("/pokemon/25")

    assert payload == {"ok": True}


@respx.mock
def test_404_raises_not_found_without_retry() -> None:
    route = respx.get(f"{BASE}/pokemon/9999").respond(404)
    client, sleeps = make_client()

    with pytest.raises(PokeApiNotFound):
        client.get_json("/pokemon/9999")

    assert route.call_count == 1
    assert all(s < 1.0 for s in sleeps)  # no backoff sleeps


@respx.mock
def test_other_4xx_fails_fast_without_retry() -> None:
    route = respx.get(f"{BASE}/pokemon/25").respond(403)
    client, _ = make_client()

    with pytest.raises(PokeApiError, match="non-transient"):
        client.get_json("/pokemon/25")

    assert route.call_count == 1


@respx.mock
def test_gives_up_after_max_attempts() -> None:
    respx.get(f"{BASE}/pokemon/25").respond(500)
    client, sleeps = make_client(max_attempts=3)

    with pytest.raises(PokeApiError, match="after 3 attempts"):
        client.get_json("/pokemon/25")

    backoffs = [s for s in sleeps if s >= 1.0]
    assert backoffs == [1.0, 2.0]  # attempts 1 and 2 backed off; attempt 3 raised
