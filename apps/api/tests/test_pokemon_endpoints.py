"""Read-endpoint unit tests against an in-memory fake repository (no DB)."""

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.schemas import (
    EvolutionChainResponse,
    EvolutionEdge,
    PokemonCard,
    PokemonSummary,
    SpeciesRef,
    TypeSlot,
)
from api.settings import ApiSettings

BULBASAUR_CARD = PokemonCard(
    id=1,
    name="bulbasaur",
    generation=1,
    color="green",
    habitat="grassland",
    is_legendary=False,
    is_mythical=False,
    height_decimetres=7,
    weight_hectograms=69,
    base_experience=64,
    types=[TypeSlot(slot=1, name="grass"), TypeSlot(slot=2, name="poison")],
    abilities=[],
    stats={"hp": 45},
    flavor_text="A strange seed...",
    sprite_kinds=["default"],
)


class InMemoryPokemonRepository:
    def __init__(self, sprite_paths: dict[str, str] | None = None) -> None:
        self.sprite_paths = sprite_paths or {}
        self.cards = {1: BULBASAUR_CARD}
        self.summaries = [
            PokemonSummary(id=1, name="bulbasaur", types=BULBASAUR_CARD.types),
            PokemonSummary(id=4, name="charmander", types=[TypeSlot(slot=1, name="fire")]),
        ]
        self.chain = EvolutionChainResponse(
            chain_id=1,
            edges=[
                EvolutionEdge(
                    from_species=SpeciesRef(id=1, name="bulbasaur"),
                    to_species=SpeciesRef(id=2, name="ivysaur"),
                    trigger="level-up",
                    min_level=16,
                    item=None,
                )
            ],
        )

    def list_pokemon(self, *, page, page_size, type_name, name_contains):
        items = self.summaries
        if type_name:
            items = [s for s in items if any(t.name == type_name for t in s.types)]
        if name_contains:
            items = [s for s in items if name_contains in s.name]
        return items[(page - 1) * page_size : page * page_size], len(items)

    def get_card(self, id_or_name):
        if id_or_name.isdigit():
            return self.cards.get(int(id_or_name))
        return next((c for c in self.cards.values() if c.name == id_or_name), None)

    def get_evolution_chain(self, id_or_name):
        return self.chain if self.get_card(id_or_name) else None

    def get_sprite(self, id_or_name, kind):
        from api.repositories import SpriteRef

        if self.get_card(id_or_name) is None or kind not in self.sprite_paths:
            return None
        return SpriteRef(pokemon_id=1, kind=kind, relative_path=self.sprite_paths[kind])


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    app.state.repository = InMemoryPokemonRepository()
    return TestClient(app)


def test_list_returns_paginated_summaries(client: TestClient) -> None:
    body = client.get("/pokemon").json()
    assert body["total"] == 2
    assert [item["name"] for item in body["items"]] == ["bulbasaur", "charmander"]


def test_list_filters_by_type(client: TestClient) -> None:
    body = client.get("/pokemon", params={"type": "fire"}).json()
    assert [item["name"] for item in body["items"]] == ["charmander"]


def test_list_rejects_invalid_pagination_with_422(client: TestClient) -> None:
    assert client.get("/pokemon", params={"page_size": 999}).status_code == 422
    assert client.get("/pokemon", params={"page": 0}).status_code == 422
    assert client.get("/pokemon", params={"type": "no;sql"}).status_code == 422


def test_get_by_id_and_by_name(client: TestClient) -> None:
    assert client.get("/pokemon/1").json()["name"] == "bulbasaur"
    assert client.get("/pokemon/bulbasaur").json()["id"] == 1


def test_get_unknown_returns_404_not_500(client: TestClient) -> None:
    response = client.get("/pokemon/9999")
    assert response.status_code == 404
    assert "9999" in response.json()["detail"]


def test_invalid_path_characters_return_422(client: TestClient) -> None:
    assert client.get("/pokemon/rm%20-rf").status_code == 422


def test_evolution_chain_shape(client: TestClient) -> None:
    body = client.get("/pokemon/1/evolution-chain").json()
    assert body["chain_id"] == 1
    edge = body["edges"][0]
    assert edge["from_species"]["name"] == "bulbasaur"
    assert edge["to_species"]["name"] == "ivysaur"
    assert edge["min_level"] == 16
