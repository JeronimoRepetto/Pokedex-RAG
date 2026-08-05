"""Response schemas for the read API."""

from pydantic import BaseModel, Field


class TypeSlot(BaseModel):
    slot: int
    name: str


class AbilityEntry(BaseModel):
    name: str
    is_hidden: bool


class PokemonSummary(BaseModel):
    id: int
    name: str
    types: list[TypeSlot]


class PokemonListResponse(BaseModel):
    items: list[PokemonSummary]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total: int = Field(ge=0)


class PokemonCard(BaseModel):
    id: int
    name: str
    generation: int
    color: str | None
    habitat: str | None
    is_legendary: bool
    is_mythical: bool
    height_decimetres: int | None
    weight_hectograms: int | None
    base_experience: int | None
    types: list[TypeSlot]
    abilities: list[AbilityEntry]
    stats: dict[str, int]
    flavor_text: str | None
    sprite_kinds: list[str]


class SpeciesRef(BaseModel):
    id: int
    name: str


class EvolutionEdge(BaseModel):
    from_species: SpeciesRef
    to_species: SpeciesRef
    trigger: str | None
    min_level: int | None
    item: str | None


class EvolutionChainResponse(BaseModel):
    chain_id: int | None
    edges: list[EvolutionEdge]
