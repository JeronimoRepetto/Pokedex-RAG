"""LLM-as-judge: groundedness/hallucination verdict on the final answer, from a model
DIFFERENT from the generator (enforced at startup in main.py — a model should never
grade its own homework). Structured output via `response_mime_type=application/json`,
not free-text parsing.

A judge failure (provider error, unparseable output) fails OPEN — assumed grounded,
with a warning — a broken judge must never take down `/chat` itself; it's a quality
gate, not a correctness gate.
"""

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from api.rag.context import BuiltContext
from pokedex_llm import GenerationRequest, LLMGateway, Message

logger = logging.getLogger(__name__)

JUDGE_SYSTEM_PROMPT = """You are a strict fact-checking judge for a Pokédex RAG system.

Given a question, a generated answer with [n] citation markers, and the numbered \
source documents the answer was generated from, assess whether every factual claim in \
the answer is actually supported by those documents.

Respond with ONLY a JSON object, no other text:
{"grounded": true or false, "hallucination": true or false, "reasoning": "<one short sentence>"}"""

JUDGE_USER_TEMPLATE = """Question: {question}

Answer to judge:
{answer}

Source documents:
{context}"""


@dataclass(frozen=True)
class JudgeVerdict:
    grounded: bool
    hallucination_detected: bool
    reasoning: str


class JudgeParsingError(RuntimeError):
    """The judge's response wasn't the expected JSON verdict shape."""


class JudgeProtocol(Protocol):
    def judge(self, question: str, answer: str, context: BuiltContext) -> JudgeVerdict: ...


class LLMJudge:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def judge(self, question: str, answer: str, context: BuiltContext) -> JudgeVerdict:
        request = GenerationRequest(
            messages=[
                Message(role="system", content=JUDGE_SYSTEM_PROMPT),
                Message(
                    role="user",
                    content=JUDGE_USER_TEMPLATE.format(
                        question=question, answer=answer, context=context.text
                    ),
                ),
            ],
            temperature=0.0,
            max_output_tokens=256,
            response_mime_type="application/json",
        )
        result = self._gateway.generate(request)
        try:
            payload = json.loads(result.text)
            return JudgeVerdict(
                grounded=bool(payload["grounded"]),
                hallucination_detected=bool(payload.get("hallucination", False)),
                reasoning=str(payload.get("reasoning", "")),
            )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise JudgeParsingError(
                f"judge returned an unparseable verdict: {result.text!r}"
            ) from exc


class FakeJudge:
    """Yields queued verdicts in order; falls back to `default` once exhausted, so
    tests that only care about the happy path don't need to script every call."""

    def __init__(
        self, script: list[JudgeVerdict] | None = None, default: JudgeVerdict | None = None
    ) -> None:
        self._script = list(script or [])
        self._default = default or JudgeVerdict(
            grounded=True, hallucination_detected=False, reasoning="looks grounded"
        )
        self.calls: list[tuple[str, str]] = []

    def judge(self, question: str, answer: str, context: BuiltContext) -> JudgeVerdict:
        self.calls.append((question, answer))
        return self._script.pop(0) if self._script else self._default
