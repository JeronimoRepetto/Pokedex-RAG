from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field

from api.search import SearchHit
from pokedex_embeddings import SpaceMismatchError

router = APIRouter(prefix="/search", tags=["search"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}


class TextSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    mode: Literal["vector", "lexical", "hybrid"] = "hybrid"
    limit: int = Field(default=10, ge=1, le=50)


class SearchResult(BaseModel):
    document_id: int
    pokemon_id: int
    pokemon_name: str
    doc_type: str
    title: str
    score: float


class SearchResponse(BaseModel):
    mode: str
    results: list[SearchResult]


def _respond(mode: str, hits: list[SearchHit]) -> SearchResponse:
    return SearchResponse(mode=mode, results=[SearchResult(**hit.__dict__) for hit in hits])


@router.post("/text", response_model=SearchResponse)
def search_text(request: Request, body: TextSearchRequest) -> SearchResponse:
    try:
        hits = request.app.state.search_service.search_text(body.query, body.mode, body.limit)
    except SpaceMismatchError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _respond(body.mode, hits)


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
    return _respond("image", hits)
