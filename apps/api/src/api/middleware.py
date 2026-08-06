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
PUBLIC_PATHS = frozenset({"/health"})


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
