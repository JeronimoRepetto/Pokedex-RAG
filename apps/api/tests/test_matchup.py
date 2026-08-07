"""Pokémon-vs-Pokémon matchup: deterministic maths, honest verdicts, no winner field."""

import pytest
from fastapi.testclient import TestClient
from test_pokemon_endpoints import BULBASAUR_CARD, InMemoryPokemonRepository

from api.main import create_app
from api.matchup import MatchupService, compute_matchup
from api.schemas import PokemonCard, TypeSlot
from api.settings import ApiSettings

SQUIRTLE_CARD = PokemonCard(
    id=7,
    name="squirtle",
    generation=1,
    color="blue",
    habitat="waters-edge",
    is_legendary=False,
    is_mythical=False,
    height_decimetres=5,
    weight_hectograms=90,
    base_experience=63,
    types=[TypeSlot(slot=1, name="water")],
    abilities=[],
    stats={"hp": 44, "attack": 48, "defense": 65, "special-attack": 50, "speed": 43},
    flavor_text="Shoots water at prey.",
    sprite_kinds=["default"],
)

CHART = {
    ("grass", "water"): 2.0,
    ("grass", "grass"): 0.5,
    ("water", "grass"): 0.5,
    ("water", "fire"): 2.0,
    ("poison", "grass"): 2.0,
    ("flying", "grass"): 2.0,
    ("fire", "grass"): 2.0,
}
ALL_TYPES = ("fire", "flying", "grass", "poison", "water")


class FakeChartLookup:
    def __init__(self, chart=None):
        self._chart = CHART if chart is None else chart

    def chart(self):
        return self._chart, ALL_TYPES


def bulbasaur_with_stats() -> PokemonCard:
    return BULBASAUR_CARD.model_copy(
        update={"stats": {"hp": 45, "attack": 49, "defense": 49, "special-attack": 65, "speed": 45}}
    )


def test_the_headline_case_bulbasaur_beats_squirtle_on_type() -> None:
    result = compute_matchup(CHART, ALL_TYPES, bulbasaur_with_stats(), SQUIRTLE_CARD)

    assert result.type_advantage == "a"
    assert result.a_side.best_multiplier == 2.0
    assert result.a_side.best_types == ("grass",)
    assert result.b_side.best_multiplier == 0.5
    assert result.b_side.verdict == "disadvantage"
    assert any("grass attacks hit Squirtle for 2x" in note for note in result.notes)


def test_stat_advantage_uses_the_base_stat_total() -> None:
    result = compute_matchup(CHART, ALL_TYPES, bulbasaur_with_stats(), SQUIRTLE_CARD)

    # 45+49+49+65+45=253 vs 44+48+65+50+43=250
    assert result.a_side.stat_total == 253
    assert result.b_side.stat_total == 250
    assert result.stat_advantage == "a"


def test_defensive_weaknesses_are_reported_per_side() -> None:
    result = compute_matchup(CHART, ALL_TYPES, bulbasaur_with_stats(), SQUIRTLE_CARD)

    assert "flying" in result.a_side.weak_to
    assert "fire" in result.a_side.weak_to


def test_no_winner_field_anywhere() -> None:
    """The honesty contract: stats + a type chart is not a battle simulator, and a
    `winner` field would be an overclaim by schema. Enforced, not remembered."""
    result = compute_matchup(CHART, ALL_TYPES, bulbasaur_with_stats(), SQUIRTLE_CARD)

    assert not hasattr(result, "winner")
    assert "not a battle simulation" in result.disclaimer


def test_service_returns_none_for_unknown_pokemon() -> None:
    service = MatchupService(InMemoryPokemonRepository(), FakeChartLookup())

    assert service.compare("bulbasaur", "agumon") is None


# --- endpoint ---------------------------------------------------------------------


@pytest.fixture
def client(tmp_path) -> TestClient:
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    repository = InMemoryPokemonRepository()
    repository.cards[7] = SQUIRTLE_CARD
    repository.cards[1] = bulbasaur_with_stats()
    app.state.matchup_service = MatchupService(repository, FakeChartLookup())
    return TestClient(app)


def test_matchup_endpoint_returns_both_sides(client) -> None:
    response = client.post("/matchup", json={"a": "bulbasaur", "b": "squirtle"})

    assert response.status_code == 200
    body = response.json()
    assert body["type_advantage"] == "a"
    assert body["a"]["name"] == "bulbasaur"
    assert body["b"]["name"] == "squirtle"
    assert "winner" not in body
    assert body["disclaimer"]


def test_matchup_accepts_numeric_ids(client) -> None:
    response = client.post("/matchup", json={"a": "1", "b": "7"})

    assert response.status_code == 200


def test_matchup_against_itself_is_rejected(client) -> None:
    response = client.post("/matchup", json={"a": "pikachu", "b": "Pikachu"})

    assert response.status_code == 422
    assert "different" in response.json()["detail"]


def test_unknown_pokemon_is_404_not_500(client) -> None:
    response = client.post("/matchup", json={"a": "bulbasaur", "b": "agumon"})

    assert response.status_code == 404


def test_malformed_names_are_rejected_at_the_boundary(client) -> None:
    assert client.post("/matchup", json={"a": "bulba saur", "b": "squirtle"}).status_code == 422
    assert client.post("/matchup", json={"a": "", "b": "squirtle"}).status_code == 422


def test_an_empty_chart_is_503_with_the_fix_in_the_message(tmp_path) -> None:
    settings = ApiSettings(database_url=f"sqlite+pysqlite:///{tmp_path}/unused.db", _env_file=None)
    app = create_app(settings)
    repository = InMemoryPokemonRepository()
    repository.cards[7] = SQUIRTLE_CARD
    app.state.matchup_service = MatchupService(repository, FakeChartLookup(chart={}))
    client = TestClient(app)

    response = client.post("/matchup", json={"a": "bulbasaur", "b": "squirtle"})

    assert response.status_code == 503
    assert "pipeline" in response.json()["detail"]
