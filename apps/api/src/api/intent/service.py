"""IntentService: deterministic rules first, LLM only for the ambiguous remainder,
and every failure degrades to `question` — the entrance to the app must never 500.
"""

import logging
from dataclasses import dataclass, field

from api.intent.classifier import ClassifierProtocol, ClassifierVerdict
from api.intent.rules import (
    QUESTION,
    VALID_INTENTS,
    Classification,
    NameLookupProtocol,
    ResolvedEntity,
    classify,
    resolve_entities,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentResult:
    intent: str
    entities: tuple[ResolvedEntity, ...]
    confidence: float
    method: str  # "deterministic" | "llm" | "fallback"
    warnings: tuple[str, ...] = field(default_factory=tuple)


class IntentService:
    def __init__(
        self,
        name_lookup: NameLookupProtocol,
        classifier: ClassifierProtocol | None = None,
        *,
        fuzzy_cutoff: float = 0.80,
        min_fuzzy_length: int = 4,
        max_entities: int = 4,
    ) -> None:
        self._name_lookup = name_lookup
        self._classifier = classifier  # None = escalation disabled by configuration
        self._fuzzy_cutoff = fuzzy_cutoff
        self._min_fuzzy_length = min_fuzzy_length
        self._max_entities = max_entities

    def resolve(self, question: str) -> IntentResult:
        names = self._name_lookup.known_names()
        entities = resolve_entities(
            question,
            names,
            cutoff=self._fuzzy_cutoff,
            min_fuzzy_length=self._min_fuzzy_length,
            limit=self._max_entities,
        )
        ruled = classify(question, entities)
        if not ruled.ambiguous or self._classifier is None:
            return IntentResult(ruled.intent, ruled.entities, ruled.confidence, "deterministic")
        return self._escalate(question, ruled, names)

    def _escalate(
        self, question: str, ruled: Classification, names: dict[str, int]
    ) -> IntentResult:
        recognised = tuple(entity.name for entity in ruled.entities)
        try:
            verdict = self._classifier.classify(question, recognised)
        except Exception as exc:  # a broken classifier must never take the endpoint down
            logger.error("intent classifier failed", extra={"error": str(exc)})
            return IntentResult(
                QUESTION,
                ruled.entities,
                0.3,
                "fallback",
                (f"classifier failed, treating as a question: {exc}",),
            )
        return self._merge(verdict, ruled, names)

    def _merge(
        self, verdict: ClassifierVerdict, ruled: Classification, names: dict[str, int]
    ) -> IntentResult:
        warnings: list[str] = []
        intent = verdict.intent if verdict.intent in VALID_INTENTS else None
        if intent is None:
            warnings.append(f"classifier returned unknown intent {verdict.intent!r}")
            intent = QUESTION

        # The model may only ADD entities that actually resolve against the roster —
        # it can suggest a name the rules missed, never invent one.
        entities = dict.fromkeys(ruled.entities)
        for name in verdict.pokemon:
            extra = resolve_entities(
                name, names, cutoff=self._fuzzy_cutoff, min_fuzzy_length=self._min_fuzzy_length
            )
            for entity in extra:
                if all(entity.id != existing.id for existing in entities):
                    entities[entity] = None
        merged = tuple(entities)[: self._max_entities]

        if intent == "compare" and len(merged) < 2:
            warnings.append("classifier chose compare but fewer than two Pokémon resolved")
            intent = QUESTION
        if intent == "card" and not merged:
            warnings.append("classifier chose card but no Pokémon resolved")
            intent = QUESTION
        return IntentResult(intent, merged, 0.7, "llm", tuple(warnings))
