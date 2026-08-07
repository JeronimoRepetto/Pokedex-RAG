"""HTTP middleware.

- `RequestIdMiddleware`: accept the caller's X-Request-ID or generate one, expose it to
  every log line via the contextvar, and always return it in the response.
- `ApiKeyMiddleware`: the deployment access gate (Phase 6.6). Disabled when no keys are
  configured, so local development and the offline test suite are unaffected.
"""

import hmac
import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from pokedex_common.request_id import new_request_id, reset_request_id, set_request_id

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
API_KEY_HEADER = "X-API-Key"
# /health must stay open: the platform's health check and uptime monitoring call it
# without credentials, and it deliberately exposes no data beyond dependency status.
# It is also how the UI tells "paused on purpose" apart from "unreachable", so it must
# keep answering while the service is paused.
PUBLIC_PATHS = frozenset({"/health"})

# Routes that can spend money. Everything else is a database read and stays available
# even when the paid allowance is gone, so a public demo degrades instead of dying.
PAID_PATHS = frozenset({"/chat", "/compare"})


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        token = set_request_id(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            reset_request_id(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request handled",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": request_id,
            },
        )
        return response


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Require a shared API key on every non-public path.

    No keys configured = gate disabled: local dev, docker-compose and the offline test
    suite keep working untouched, while the deployed service sets API_KEYS and becomes
    closed by default. Keys are compared in constant time and NEVER logged — a rejected
    request logs only the path and the fact that a key was missing vs wrong.
    """

    def __init__(self, app, api_keys: frozenset[str] | set[str] | None = None) -> None:
        super().__init__(app)
        self._api_keys = frozenset(api_keys or ())

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._api_keys or request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        provided = request.headers.get(API_KEY_HEADER)
        if provided is None:
            return self._denied(request, "missing")
        if not any(hmac.compare_digest(provided, key) for key in self._api_keys):
            return self._denied(request, "invalid")
        return await call_next(request)

    def _denied(self, request: Request, reason: str) -> JSONResponse:
        logger.warning(
            "api key rejected",
            extra={"path": request.url.path, "method": request.method, "reason": reason},
        )
        return JSONResponse(
            status_code=401,
            content={"detail": f"{API_KEY_HEADER} header is {reason}"},
            headers={"WWW-Authenticate": API_KEY_HEADER},
        )


class PausedMiddleware(BaseHTTPMiddleware):
    """Turns the whole service off without deleting it.

    While paused, no route handler runs, so no model can be called no matter what a
    caller sends. /health stays up on purpose: it is the only way the UI can distinguish
    "the owner paused this" from "the service is broken", and the two deserve different
    messages.

    Flipped with a single `gcloud run services update --update-env-vars SERVICE_PAUSED=`,
    which takes about fifteen seconds.
    """

    def __init__(self, app, paused: bool = False, contact: str = "") -> None:
        super().__init__(app)
        self._paused = paused
        self._contact = contact

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._paused or request.url.path in PUBLIC_PATHS:
            return await call_next(request)
        suffix = f" Contact: {self._contact}." if self._contact else ""
        return JSONResponse(
            status_code=503,
            content={
                "paused": True,
                "detail": (
                    "This demo is paused to keep it free to run. "
                    f"Ask the developer to switch it back on.{suffix}"
                ),
                "detail_es": (
                    "Esta demo está pausada para que no genere coste. "
                    f"Pedile al desarrollador que la active.{suffix}"
                ),
            },
        )


class PaidRouteLimitMiddleware(BaseHTTPMiddleware):
    """Per-caller daily cap on the routes that cost money.

    This is the second of three independent layers (the others being the global quota
    inside the gateway and the project's billing guard). It exists so one abusive caller
    cannot consume the whole day's global allowance on their own.
    """

    def __init__(self, app, counter=None, per_caller_limit: int = 0) -> None:
        super().__init__(app)
        self._counter = counter
        self._limit = per_caller_limit

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._counter is None or self._limit <= 0 or request.url.path not in PAID_PATHS:
            return await call_next(request)

        from api.quota import hash_caller

        bucket = hash_caller(_client_identifier(request))
        used = self._counter.increment(bucket)
        if used > self._limit:
            logger.warning(
                "per-caller limit reached",
                extra={"path": request.url.path, "used": used, "limit": self._limit},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "detail": (
                        f"You have used this demo's {self._limit} AI answers for today. "
                        "Browsing Pokémon, search and type matchups still work."
                    ),
                    "detail_es": (
                        f"Ya usaste las {self._limit} respuestas con IA de hoy. "
                        "Las fichas, la búsqueda y las ventajas de tipo siguen disponibles."
                    ),
                },
            )
        return await call_next(request)


def _client_identifier(request: Request) -> str:
    """Cloud Run puts the real client first in X-Forwarded-For; behind no proxy we fall
    back to the socket address. Only ever fed to a hash — never stored or logged."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
