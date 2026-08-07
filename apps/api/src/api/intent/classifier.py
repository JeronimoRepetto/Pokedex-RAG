"""LLM escalation for genuinely ambiguous input.

Follows LLMJudge exactly: structured JSON via `response_mime_type`, prompts as module
constants beside the component, hand-coerced into a frozen dataclass.

The model chooses a LABEL ONLY. Any names it mentions are re-resolved against the real
roster by the caller and dropped if they do not resolve — the classifier can never mint
a Pokémon that does not exist.
"""

import json
import logging
from dataclasses import dataclass
from typing import Protocol

from pokedex_llm import GenerationRequest, LLMGateway, Message

logger = logging.getLogger(__name__)

INTENT_SYSTEM_PROMPT = """You classify what a user wants from a Pokédex application.

Choose exactly one intent:
- "card": they want to see one Pokémon's entry (its stats, types, description).
- "question": they ask something specific that needs an explanation.
- "compare": they want two or more Pokémon compared against each other.

The user may write in any language, most often English or Spanish.

Respond with ONLY a JSON object, no other text:
{"intent": "card" | "question" | "compare", "pokemon": ["<names you see>"], \
"reasoning": "<one short sentence>"}"""

INTENT_USER_TEMPLATE = """User input: {question}

Pokémon already recognised in it: {recognised}"""


class IntentParsingError(RuntimeError):
    """The classifier's response wasn't the expected JSON shape."""


@dataclass(frozen=True)
class ClassifierVerdict:
    intent: str
    pokemon: tuple[str, ...]
    reasoning: str


class ClassifierProtocol(Protocol):
    def classify(self, question: str, recognised: tuple[str, ...]) -> ClassifierVerdict: ...


class LLMIntentClassifier:
    def __init__(self, gateway: LLMGateway, max_output_tokens: int = 128) -> None:
        self._gateway = gateway
        self._max_output_tokens = max_output_tokens

    def classify(self, question: str, recognised: tuple[str, ...]) -> ClassifierVerdict:
        request = GenerationRequest(
            messages=[
                Message(role="system", content=INTENT_SYSTEM_PROMPT),
                Message(
                    role="user",
                    content=INTENT_USER_TEMPLATE.format(
                        question=question,
                        recognised=", ".join(recognised) if recognised else "none",
                    ),
                ),
            ],
            temperature=0.0,
            max_output_tokens=self._max_output_tokens,
            response_mime_type="application/json",
        )
        result = self._gateway.generate(request)
        try:
            payload = json.loads(result.text)
            intent = str(payload["intent"]).strip().lower()
            names = payload.get("pokemon") or []
            return ClassifierVerdict(
                intent=intent,
                pokemon=tuple(str(name).strip().lower() for name in names),
                reasoning=str(payload.get("reasoning", "")),
            )
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
            raise IntentParsingError(
                f"classifier returned an unparseable verdict: {result.text!r}"
            ) from exc


class FakeIntentClassifier:
    """Queued verdicts, then a default — mirrors FakeJudge so tests read the same way."""

    def __init__(
        self,
        script: list[ClassifierVerdict | Exception] | None = None,
        default: ClassifierVerdict | None = None,
    ) -> None:
        self._script = list(script or [])
        self._default = default or ClassifierVerdict("question", (), "fake")
        self.calls: list[tuple[str, tuple[str, ...]]] = []

    def classify(self, question: str, recognised: tuple[str, ...]) -> ClassifierVerdict:
        self.calls.append((question, recognised))
        item = self._script.pop(0) if self._script else self._default
        if isinstance(item, Exception):
            raise item
        return item
