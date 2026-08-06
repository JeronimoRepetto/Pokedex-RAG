"""Offline stand-in for `ApiClient` — the pipeline-integrity harness (Phase 6.3).

`evals run --fake-api` exercises the WHOLE runner without a network, an API, a
database of vectors or a cent of spend: case files parse, the client contract is
honored, every suite branch runs, scoring and summaries compute, persistence writes.

Deliberately, responses are derived from a hash of the query — NOT from the case's
`expected` block. A fake that echoed expectations would score 1.000 every time, which
means a scorer stubbed to `return 1.0` would sail through CI. Here the scores are
arbitrary and CI asserts that the pipeline RAN, not that it scored well.
"""

import hashlib
from pathlib import Path

GEN1_MAX = 151


def _ids_for(seed: str, count: int) -> list[int]:
    """Deterministic, seed-dependent, duplicate-free Gen-1 ids."""
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    ids: list[int] = []
    for byte in digest:
        candidate = byte % GEN1_MAX + 1
        if candidate not in ids:
            ids.append(candidate)
        if len(ids) == count:
            break
    return ids


class FakeApiClient:
    """Same surface as `ApiClient`; records every call for assertions."""

    def __init__(self, base_url: str = "fake://offline") -> None:
        self.base_url = base_url
        self.calls: list[tuple[str, str]] = []

    def search_text(
        self, query: str, mode: str = "hybrid", limit: int = 10, space: str | None = None
    ) -> dict:
        self.calls.append(("search_text", query))
        return {
            "mode": mode,
            "space": space or "fake-space",
            "results": [
                {
                    "document_id": pokemon_id,
                    "pokemon_id": pokemon_id,
                    "pokemon_name": f"pokemon-{pokemon_id}",
                    "doc_type": "card",
                    "title": f"Pokemon {pokemon_id}",
                    "score": round(1.0 - index / 100, 4),
                }
                for index, pokemon_id in enumerate(_ids_for(query, limit))
            ],
        }

    def search_image(self, image_path: Path, limit: int = 10) -> dict:
        """The file is never opened: visual cases must run in CI without sprite
        binaries, which are gitignored by IP policy."""
        self.calls.append(("search_image", str(image_path)))
        return {
            "mode": "image",
            "results": [
                {
                    "document_id": pokemon_id,
                    "pokemon_id": pokemon_id,
                    "pokemon_name": f"pokemon-{pokemon_id}",
                    "doc_type": "sprite",
                    "title": f"Pokemon {pokemon_id} sprite",
                    "score": round(1.0 - index / 100, 4),
                }
                for index, pokemon_id in enumerate(_ids_for(Path(image_path).name, limit))
            ],
        }

    def chat(self, question: str, provider: str | None = None) -> dict:
        self.calls.append(("chat", question))
        return {
            "status": "answered",
            "answer": f"Offline fake answer for {question!r} [1].",
            "citations": [{"marker": 1, "document_id": str(_ids_for(question, 1)[0])}],
            "confidence": None,
            "warnings": ["fake-api response: not a real generation"],
            "corrections_applied": 0,
            "evaluation_id": None,
            "request_id": "fake-request-id",
        }

    def compare(self, question: str, providers: list[str] | None = None) -> dict:
        self.calls.append(("compare", question))
        names = providers or ["fake-primary", "fake-fallback"]
        return {
            "question": question,
            "request_id": "fake-request-id",
            "context_document_ids": _ids_for(question, 3),
            "context_chars": len(question) * 10,
            "candidates": [
                {
                    "provider": name,
                    "model": f"{name}-model",
                    "status": "answered",
                    "answer": f"Offline fake answer from {name} [1].",
                    "citations": [],
                    "warnings": ["fake-api response: not a real generation"],
                    "corrections_applied": 0,
                    "judge": {
                        "grounded": True,
                        "hallucination_detected": False,
                        "reasoning": "fake verdict",
                        "independent": True,
                    },
                    "latency_ms": 10 + index,
                    "prompt_tokens": 100,
                    "output_tokens": 20,
                }
                for index, name in enumerate(names)
            ],
        }

    def close(self) -> None:
        return None

    def __enter__(self) -> "FakeApiClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
