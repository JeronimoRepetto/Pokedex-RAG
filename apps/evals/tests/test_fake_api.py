"""The offline pipeline-integrity harness (Phase 6.3)."""

from pathlib import Path

import respx
from typer.testing import CliRunner

from evals.cli import app
from evals.fakes import FakeApiClient

runner = CliRunner()


def test_responses_are_deterministic_per_query() -> None:
    client = FakeApiClient()

    first = client.search_text("what type is bulbasaur")
    second = client.search_text("what type is bulbasaur")

    assert first == second


def test_different_queries_give_different_results() -> None:
    client = FakeApiClient()

    bulbasaur = client.search_text("what type is bulbasaur")
    charizard = client.search_text("what type is charizard")

    assert bulbasaur["results"] != charizard["results"]


def test_hits_are_distinct_valid_gen1_ids() -> None:
    hits = FakeApiClient().search_text("anything", limit=10)["results"]
    ids = [hit["pokemon_id"] for hit in hits]

    assert len(ids) == len(set(ids))
    assert all(1 <= pokemon_id <= 151 for pokemon_id in ids)


def test_image_search_never_opens_the_file() -> None:
    """Sprites are gitignored, so CI has no image files to open."""
    result = FakeApiClient().search_image(Path("sprites/does-not-exist.png"), limit=3)

    assert len(result["results"]) == 3
    assert result["mode"] == "image"


def test_chat_and_compare_shapes_match_the_real_contract() -> None:
    client = FakeApiClient()

    chat = client.chat("what type is bulbasaur?")
    comparison = client.compare("what type is bulbasaur?", providers=["a", "b"])

    assert set(chat) >= {"status", "answer", "citations", "warnings", "request_id"}
    assert [c["provider"] for c in comparison["candidates"]] == ["a", "b"]
    assert set(comparison["candidates"][0]) >= {
        "provider",
        "model",
        "status",
        "answer",
        "citations",
        "judge",
        "latency_ms",
        "prompt_tokens",
        "output_tokens",
    }


def test_answers_are_labelled_as_fake() -> None:
    """Nothing produced by this client may ever be mistaken for a real generation."""
    client = FakeApiClient()

    assert "fake" in client.chat("q")["warnings"][0]
    assert "fake" in client.compare("q")["candidates"][0]["warnings"][0]


@respx.mock
def test_fake_api_run_makes_no_http_calls(tmp_path) -> None:
    (tmp_path / "text_retrieval_001.yaml").write_text(
        """case_id: text_retrieval_001
suite: text_retrieval
input:
  query: "what type is bulbasaur"
  mode: hybrid
  limit: 5
expected:
  relevant_pokemon_ids: [1]
origin: handwritten
""",
        encoding="utf-8",
    )
    route = respx.post("http://localhost:8000/search/text")

    result = runner.invoke(app, ["run", "--cases-dir", str(tmp_path), "--fake-api"])

    assert result.exit_code == 0
    assert not route.called
    assert "suite averages" in result.output


def test_fake_api_scores_are_not_derived_from_expectations(tmp_path) -> None:
    """A fake that echoed `expected` would let a scorer stubbed to 1.0 pass CI. This
    case expects Pokémon #1 and the fake does not know that."""
    (tmp_path / "text_retrieval_001.yaml").write_text(
        """case_id: text_retrieval_001
suite: text_retrieval
input:
  query: "what type is bulbasaur"
  mode: hybrid
  limit: 5
expected:
  relevant_pokemon_ids: [1]
origin: handwritten
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["run", "--cases-dir", str(tmp_path), "--fake-api"])

    assert result.exit_code == 0
    assert "recall_at_k=1.000" not in result.output
