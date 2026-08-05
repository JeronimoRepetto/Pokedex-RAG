"""/health: verifies real dependencies and answers 200 or 503 with per-dependency
detail. New dependencies (Vertex AI, Langfuse) register here as they land."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

router = APIRouter()


def check_database(engine) -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}


@router.get("/health")
def health(request: Request) -> JSONResponse:
    dependencies = {"database": check_database(request.app.state.engine)}
    healthy = all(dep["status"] == "ok" for dep in dependencies.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ok" if healthy else "degraded", "dependencies": dependencies},
    )
