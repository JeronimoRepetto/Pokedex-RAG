from pathlib import Path as FilePath
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import FileResponse

from api.repositories import PokemonReadRepository
from api.schemas import EvolutionChainResponse, PokemonCard, PokemonListResponse

router = APIRouter(prefix="/pokemon", tags=["pokedex"])

SPRITE_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

IdOrName = Annotated[
    str,
    Path(
        max_length=100,
        pattern=r"^[a-zA-Z0-9-]+$",
        description="PokéAPI numeric id or lowercase name",
    ),
]


def get_repository(request: Request) -> PokemonReadRepository:
    return request.app.state.repository


@router.get("", response_model=PokemonListResponse)
def list_pokemon(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    type: Annotated[str | None, Query(max_length=50, pattern=r"^[a-zA-Z-]+$")] = None,
    name: Annotated[str | None, Query(max_length=100, pattern=r"^[a-zA-Z0-9-]+$")] = None,
) -> PokemonListResponse:
    items, total = get_repository(request).list_pokemon(
        page=page, page_size=page_size, type_name=type, name_contains=name
    )
    return PokemonListResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{id_or_name}", response_model=PokemonCard)
def get_pokemon(request: Request, id_or_name: IdOrName) -> PokemonCard:
    card = get_repository(request).get_card(id_or_name)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Pokemon {id_or_name!r} not found")
    return card


@router.get("/{id_or_name}/evolution-chain", response_model=EvolutionChainResponse)
def get_evolution_chain(request: Request, id_or_name: IdOrName) -> EvolutionChainResponse:
    chain = get_repository(request).get_evolution_chain(id_or_name)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Pokemon {id_or_name!r} not found")
    return chain


@router.get(
    "/{id_or_name}/sprite",
    response_class=FileResponse,
    responses={200: {"content": {"image/png": {}}}, 404: {"description": "No such sprite"}},
)
def get_sprite(
    request: Request,
    id_or_name: IdOrName,
    kind: Annotated[str, Query(max_length=50, pattern=r"^[a-z0-9-]+$")] = "official-artwork",
) -> FileResponse:
    """Serve a downloaded sprite file.

    The bytes live under DATA_DIR (gitignored, never in the repo). This endpoint exists
    so the web UI can show images while consuming ONLY the public API — no direct disk
    or database access from the browser, and no hotlinking someone else's bandwidth.
    """
    reference = get_repository(request).get_sprite(id_or_name, kind)
    if reference is None:
        raise HTTPException(
            status_code=404, detail=f"No {kind!r} sprite for Pokemon {id_or_name!r}"
        )
    data_dir = FilePath(request.app.state.settings.data_dir).resolve()
    file_path = (data_dir / reference.relative_path).resolve()
    # Defence in depth: local_path comes from our own ingest, but a stored value that
    # escaped DATA_DIR would turn this endpoint into an arbitrary-file reader.
    if not file_path.is_relative_to(data_dir) or not file_path.is_file():
        raise HTTPException(
            status_code=404, detail=f"Sprite file for Pokemon {id_or_name!r} is not on disk"
        )
    return FileResponse(
        file_path,
        media_type=SPRITE_MEDIA_TYPES.get(file_path.suffix.lower(), "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=86400"},
    )
