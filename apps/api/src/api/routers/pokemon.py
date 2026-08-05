from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request

from api.repositories import PokemonReadRepository
from api.schemas import EvolutionChainResponse, PokemonCard, PokemonListResponse

router = APIRouter(prefix="/pokemon", tags=["pokedex"])

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
