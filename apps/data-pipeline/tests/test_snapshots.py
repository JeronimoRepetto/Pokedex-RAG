import hashlib
import json
from pathlib import Path

import pytest

from pipeline.snapshots import SnapshotStore
from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base


@pytest.fixture
def store(tmp_path: Path) -> SnapshotStore:
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return SnapshotStore(create_session_factory(engine), tmp_path)


def test_save_writes_file_and_row_with_matching_hash(store: SnapshotStore, tmp_path: Path) -> None:
    payload = {"name": "pikachu", "id": 25}

    snapshot, created = store.save(
        "pokemon", "25", "https://pokeapi.co/api/v2/pokemon/25/", payload
    )

    assert created is True
    file_path = tmp_path / "raw" / "pokeapi" / "pokemon" / "25.json"
    assert file_path.exists()
    body = file_path.read_bytes()
    assert json.loads(body) == payload
    assert snapshot.sha256 == hashlib.sha256(body).hexdigest()
    assert snapshot.payload == payload


def test_save_is_idempotent(store: SnapshotStore, tmp_path: Path) -> None:
    first, created_first = store.save("pokemon", "25", "https://x/25/", {"id": 25})
    file_path = tmp_path / "raw" / "pokeapi" / "pokemon" / "25.json"
    original_bytes = file_path.read_bytes()

    second, created_second = store.save(
        "pokemon", "25", "https://x/25/", {"id": 25, "mutated": True}
    )

    assert created_first is True
    assert created_second is False
    assert second.id == first.id
    assert file_path.read_bytes() == original_bytes  # immutable: never rewritten
    assert store.exists("pokemon", "25") is True


def test_exists_is_false_for_unknown_resource(store: SnapshotStore) -> None:
    assert store.exists("pokemon", "9999") is False
