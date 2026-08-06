"""`evals compare` CLI: per-provider scoring off one /compare call per case."""

import json

import respx
from typer.testing import CliRunner

from evals.cli import app

runner = CliRunner()
BASE = "http://api.test"


def write_rag_case(directory, case_id: str = "rag_quality_001") -> None:
    (directory / f"{case_id}.yaml").write_text(
        f"""case_id: {case_id}
suite: rag_quality
input:
  question: "what type is bulbasaur?"
expected:
  status: answered
  must_contain: [grass]
origin: handwritten
""",
        encoding="utf-8",
    )


def compare_payload(**overrides) -> dict:
    base = {
        "question": "what type is bulbasaur?",
        "request_id": "r1",
        "context_document_ids": [1, 2],
        "context_chars": 400,
        "candidates": [
            {
                "provider": "vertex-gemini",
                "model": "gemini-3.6-flash",
                "status": "answered",
                "answer": "Bulbasaur is grass/poison [1].",
                "citations": [],
                "warnings": [],
                "corrections_applied": 0,
                "judge": {"grounded": True, "hallucination_detected": False, "reasoning": "ok"},
                "latency_ms": 800,
                "prompt_tokens": 500,
                "output_tokens": 30,
            },
            {
                "provider": "ai-studio-gemini",
                "model": "gemini-3.5-flash-lite",
                "status": "answered",
                "answer": "Bulbasaur is a fire type [1].",
                "citations": [],
                "warnings": [],
                "corrections_applied": 0,
                "judge": {"grounded": False, "hallucination_detected": True, "reasoning": "wrong"},
                "latency_ms": 400,
                "prompt_tokens": 500,
                "output_tokens": 25,
            },
        ],
    }
    return {**base, **overrides}


@respx.mock
def test_compare_scores_each_provider_separately(tmp_path) -> None:
    write_rag_case(tmp_path)
    respx.post(f"{BASE}/compare").respond(json=compare_payload())

    result = runner.invoke(app, ["compare", "--cases-dir", str(tmp_path), "--api-url", BASE])

    assert result.exit_code == 0
    assert "[vertex-gemini]" in result.output
    assert "[ai-studio-gemini]" in result.output
    # vertex satisfied must_contain=grass; ai-studio said "fire" and failed it
    assert "pass_rate=1.000" in result.output
    assert "pass_rate=0.000" in result.output
    assert "ran 1 case(s) against 2 provider(s)" in result.output


@respx.mock
def test_compare_forwards_requested_providers(tmp_path) -> None:
    write_rag_case(tmp_path)
    route = respx.post(f"{BASE}/compare").respond(json=compare_payload())

    result = runner.invoke(
        app,
        [
            "compare",
            "--cases-dir",
            str(tmp_path),
            "--api-url",
            BASE,
            "--providers",
            "vertex-gemini",
            "--providers",
            "ai-studio-gemini",
        ],
    )

    assert result.exit_code == 0
    sent = json.loads(route.calls[0].request.content)
    assert sent["providers"] == ["vertex-gemini", "ai-studio-gemini"]


@respx.mock
def test_compare_omits_providers_when_not_given(tmp_path) -> None:
    write_rag_case(tmp_path)
    route = respx.post(f"{BASE}/compare").respond(json=compare_payload())

    runner.invoke(app, ["compare", "--cases-dir", str(tmp_path), "--api-url", BASE])

    assert "providers" not in json.loads(route.calls[0].request.content)


def test_compare_rejects_cases_without_a_question(tmp_path) -> None:
    """text_retrieval cases carry `query`, not `question` — /compare cannot run them,
    and silently skipping would make an empty report look like a passing one."""
    (tmp_path / "text_retrieval_001.yaml").write_text(
        """case_id: text_retrieval_001
suite: text_retrieval
input:
  query: "what type is bulbasaur"
expected:
  relevant_pokemon_ids: [1]
origin: handwritten
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["compare", "--cases-dir", str(tmp_path), "--suite", "text_retrieval", "--api-url", BASE],
    )

    assert result.exit_code == 1
    assert "question-shaped" in result.output


def test_compare_with_no_cases_exits_nonzero(tmp_path) -> None:
    result = runner.invoke(app, ["compare", "--cases-dir", str(tmp_path), "--api-url", BASE])

    assert result.exit_code == 1
