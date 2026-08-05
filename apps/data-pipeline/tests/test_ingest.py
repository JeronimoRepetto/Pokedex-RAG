import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select

from pipeline.ingest import ingest_generation
from pipeline.snapshots import SnapshotStore
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Ability, Base, Evolution, Move, Pokemon, RawSnapshot, Species, Type

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakePokeApiClient:
    """Deterministic in-memory PokéAPI. Records every fetched path."""

    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads
        self.calls: list[str] = []

    def get_json(self, path: str) -> tuple[dict[str, Any], str]:
        self.calls.append(path)
        if path not in self.payloads:
            raise AssertionError(f"unexpected fetch: {path}")
        return self.payloads[path], f"https://pokeapi.test/api/v2{path}"


def mini_universe() -> dict[str, dict[str, Any]]:
    return {
        "/generation/1": load("generation_1.json"),
        "/pokemon-species/1": load("species_bulbasaur.json"),
        "/pokemon/1": load("pokemon_bulbasaur.json"),
        "/evolution-chain/1": load("evolution_chain_1.json"),
        "/type/4": {"id": 4, "name": "poison"},
        "/type/12": {"id": 12, "name": "grass"},
        "/ability/34": {"id": 34, "name": "chlorophyll", "effect_entries": []},
        "/ability/65": load("ability_overgrow.json"),
        "/move/33": {"id": 33, "name": "tackle", "power": 40, "accuracy": 100, "pp": 35},
        "/move/75": load("move_razor_leaf.json"),
    }


@pytest.fixture
def env(tmp_path: Path):
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = create_session_factory(engine)
    store = SnapshotStore(session_factory, tmp_path)
    return session_factory, store


def test_ingest_builds_full_mini_universe(env) -> None:
    session_factory, store = env
    client = FakePokeApiClient(mini_universe())

    report = ingest_generation(client, store, session_factory, generation=1)

    assert report.fetched == 10
    assert report.reused == 0
    with session_factory() as session:
        assert session.get(Species, 1).name == "bulbasaur"
        assert session.get(Pokemon, 1).species_id == 1
        assert session.get(Type, 12).name == "grass"
        assert session.get(Ability, 65).effect_text.startswith("Strengthens")
        assert session.get(Move, 75).power == 55
        # snapshots recorded for every fetch
        count = session.execute(select(func.count()).select_from(RawSnapshot)).scalar_one()
        assert count == 10
        # ivysaur/venusaur are outside the ingested set -> edges skipped, none broken
        assert session.execute(select(func.count()).select_from(Evolution)).scalar_one() == 0


def test_second_run_fetches_nothing(env) -> None:
    session_factory, store = env
    first_client = FakePokeApiClient(mini_universe())
    ingest_generation(first_client, store, session_factory)

    second_client = FakePokeApiClient(mini_universe())
    report = ingest_generation(second_client, store, session_factory)

    assert second_client.calls == []  # PokéAPI fair use: every resource fetched once, ever
    assert report.fetched == 0
    assert report.reused == 10
