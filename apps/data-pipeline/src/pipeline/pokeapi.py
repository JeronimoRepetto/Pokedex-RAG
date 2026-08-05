"""PokéAPI HTTP client.

Fair-use rules baked in: throttled request rate, explicit timeout, exponential backoff
ONLY on transient failures (429/5xx/transport errors), bounded attempts, every retry
logged. Non-transient responses fail fast. PokéAPI asks consumers to cache locally —
the ingest flow calls this client at most once per resource (see snapshots.py).
"""

import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class PokeApiError(RuntimeError):
    """Unexpected response or transient failures exhausted all attempts."""


class PokeApiNotFound(PokeApiError):
    """The resource does not exist (HTTP 404)."""


class PokeApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30.0,
        rate_limit_per_sec: float = 3.0,
        max_attempts: int = 4,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, timeout=timeout_seconds)
        self._min_interval = 1.0 / rate_limit_per_sec
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "PokeApiClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def get_json(self, path: str) -> tuple[dict[str, Any], str]:
        """GET a resource; returns (payload, final URL). Retries transient failures."""
        last_error: str = "unknown"
        for attempt in range(1, self._max_attempts + 1):
            self._throttle()
            try:
                response = self._client.get(path)
            except httpx.TransportError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            else:
                if response.status_code == httpx.codes.OK:
                    return response.json(), str(response.url)
                if response.status_code == httpx.codes.NOT_FOUND:
                    raise PokeApiNotFound(f"PokéAPI resource not found: {response.url}")
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"HTTP {response.status_code}"
                else:
                    raise PokeApiError(
                        f"Unexpected HTTP {response.status_code} from {response.url}; "
                        "not retrying (non-transient)."
                    )
            if attempt < self._max_attempts:
                delay = self._backoff_base * 2 ** (attempt - 1)
                logger.warning(
                    "pokeapi retry",
                    extra={
                        "path": path,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "reason": last_error,
                        "backoff_seconds": delay,
                    },
                )
                self._sleep(delay)
        raise PokeApiError(
            f"Gave up on {path} after {self._max_attempts} attempts; last error: {last_error}"
        )

    def _throttle(self) -> None:
        if self._last_request_at is not None:
            wait = self._min_interval - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()
