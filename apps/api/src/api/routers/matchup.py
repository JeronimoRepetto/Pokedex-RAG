from typing import Annotated

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, StringConstraints

from api.matchup import MatchupUnavailableError
from api.schemas import PokemonCard

router = APIRouter(tags=["matchup"])

IdOrNameField = Annotated[
    str, StringConstraints(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9-]+$")
]


class MatchupRequest(BaseModel):
    a: IdOrNameField
    b: IdOrNameField


class SideOut(BaseModel):
    name: str
    best_multiplier: float
    best_types: list[str]
    verdict: str
    weak_to: list[str]
    immune_to: list[str]
    stat_total: int


class MatchupResponse(BaseModel):
    a: PokemonCard
    b: PokemonCard
    a_side: SideOut
    b_side: SideOut
    type_advantage: str
    stat_advantage: str
    notes: list[str]
    disclaimer: str


@router.post("/matchup", response_model=MatchupResponse)
def compare_pokemon(request: Request, body: MatchupRequest) -> MatchupResponse:
    """Deterministic head-to-head: cards, stat totals and type-chart maths. No LLM.

    (Provider comparison lives at /compare; this compares Pokémon.)
    """
    if body.a.lower() == body.b.lower():
        raise HTTPException(
            status_code=422,
            detail="a and b must be different Pokémon — a matchup against itself says nothing",
        )
    try:
        result = request.app.state.matchup_service.compare(body.a.lower(), body.b.lower())
    except MatchupUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown Pokémon in matchup: {body.a!r} vs {body.b!r}"
        )
    return MatchupResponse(
        a=result.a,
        b=result.b,
        a_side=SideOut(**vars(result.a_side)),
        b_side=SideOut(**vars(result.b_side)),
        type_advantage=result.type_advantage,
        stat_advantage=result.stat_advantage,
        notes=list(result.notes),
        disclaimer=result.disclaimer,
    )
