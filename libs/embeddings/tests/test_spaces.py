import pytest

from pokedex_db.engine import create_db_engine, create_session_factory
from pokedex_db.models import Base, EmbeddingSpace
from pokedex_embeddings import SpaceConfig, SpaceMismatchError, verify_embedding_space

CONFIG = SpaceConfig(
    label="gemini-embedding-2-768-v1", model_name="gemini-embedding-2", dimensions=768
)


@pytest.fixture
def session_factory():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return create_session_factory(engine)


def seed_space(session, **overrides) -> None:
    defaults = {
        "label": CONFIG.label,
        "model_name": CONFIG.model_name,
        "dimensions": CONFIG.dimensions,
        "modality": "multimodal",
    }
    defaults.update(overrides)
    session.add(EmbeddingSpace(**defaults))
    session.commit()


def test_matching_registry_returns_space_id(session_factory) -> None:
    with session_factory() as session:
        seed_space(session)
        assert verify_embedding_space(session, CONFIG) == 1


def test_unregistered_space_fails_with_migration_hint(session_factory) -> None:
    with session_factory() as session, pytest.raises(SpaceMismatchError, match="db upgrade"):
        verify_embedding_space(session, CONFIG)


def test_model_mismatch_reports_expected_and_found(session_factory) -> None:
    with session_factory() as session:
        seed_space(session, model_name="some-other-model")
        with pytest.raises(SpaceMismatchError) as excinfo:
            verify_embedding_space(session, CONFIG)
        message = str(excinfo.value)
        assert "some-other-model" in message
        assert "gemini-embedding-2" in message


def test_dimension_mismatch_is_detected(session_factory) -> None:
    with session_factory() as session:
        seed_space(session, dimensions=1536)
        with pytest.raises(SpaceMismatchError, match="1536"):
            verify_embedding_space(session, CONFIG)
