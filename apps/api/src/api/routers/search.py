from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from api.search import SearchHit
from pokedex_embeddings import EmbeddingError, SpaceMismatchError

router = APIRouter(prefix="/search", tags=["search"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


class TextSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    mode: Literal["vector", "lexical", "hybrid"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=50)
    # Embedding space to search in; None = the primary space. Allowlisted against the
    # spaces registered at startup — results from different spaces never mix.
    space: str | None = Field(default=None, max_length=100)


class SearchResult(BaseModel):
    document_id: int
    pokemon_id: int
    pokemon_name: str
    doc_type: str
    title: str
    score: float


class SearchResponse(BaseModel):
    mode: str
    space: str = ""
    results: list[SearchResult]


def _respond(mode: str, hits: list[SearchHit], space: str = "") -> SearchResponse:
    return SearchResponse(
        mode=mode, space=space, results=[SearchResult(**hit.__dict__) for hit in hits]
    )


@router.post("/text", response_model=SearchResponse)
def search_text(request: Request, body: TextSearchRequest) -> SearchResponse:
    if body.space is None:
        service = request.app.state.search_service
        space_label = request.app.state.settings.embedding_space_label
    else:
        service = request.app.state.search_services.get(body.space)
        space_label = body.space
        if service is None:
            known = sorted(label for label in request.app.state.search_services if label)
            raise HTTPException(
                status_code=422,
                detail=f"Unknown embedding space {body.space!r}; available: {known}",
            )
    try:
        hits = service.search_text(body.query, body.mode, body.limit)
    except SpaceMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmbeddingError as exc:
        # Provider/dependency failure (exhausted retries, missing optional model
        # runtime): the request was valid, the backend is what's unavailable.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _respond(body.mode, hits, space_label)


@router.post("/image", response_model=SearchResponse)
async def search_image(
    request: Request,
    image: Annotated[UploadFile, File(description="Sprite or artwork to search by")],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SearchResponse:
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported image type {image.content_type!r}; "
            f"allowed: {sorted(ALLOWED_IMAGE_TYPES)}",
        )
    data = await image.read()
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image larger than 5 MB")
    if not data:
        raise HTTPException(status_code=422, detail="Empty image upload")
    try:
        hits = request.app.state.search_service.search_image(data, image.content_type, limit)
    except SpaceMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmbeddingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _respond("image", hits, request.app.state.settings.embedding_space_label)
