"""Deterministic intent rules: resolve Pokémon names, then classify by cue words.

This is the free path. It answers the overwhelming majority of real queries with no
model call at all, which matters because /intent is hit on EVERY submission — if it
escalated by default it would quietly become the most expensive endpoint in the product.

Everything here is bilingual: the user writes Spanish, the golden dataset is English.
"""

import difflib
import unicodedata
from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

CARD = "card"
QUESTION = "question"
COMPARE = "compare"
VALID_INTENTS = (CARD, QUESTION, COMPARE)

# Words that must NEVER be fuzzy-matched to a Pokémon. This list is not decoration:
# Spanish "para" scores 0.889 against "paras" (the Gen-1 mushroom), which clears any
# usable cutoff, so "¿cuál es mejor para atacar?" would silently resolve an entity and
# mis-route the whole request. Measured, not guessed.
_STOPWORDS_ES = (
    "a al algo como con contra cual cuales cuando cuanto de del dime donde dos el ella "
    "ellos en entre era eres es esa ese eso esta este esto fuerte gana ganar hay la las "
    "le lo los mas me mejor mi muestra muestrame mucho muy no nos o para pero por porque "
    "que quien quienes se ser si sobre su sus te tiene todo todos tu un una uno vs y ya"
)
_STOPWORDS_EN = (
    "about all and are best better between both can compare could does for from get give "
    "has have how in is it its me more most much of on or show stronger tell than that "
    "the their them then there these they this to told two was what when where which who "
    "whom why will with would you your"
)
STOPWORDS = frozenset(f"{_STOPWORDS_ES} {_STOPWORDS_EN}".split())

# Cue phrases. Checked against the accent-folded, lowercased text.
COMPARE_CUES = (
    "vs",
    "versus",
    "contra",
    "mas fuerte",
    "mas debil",
    "mejor que",
    "quien gana",
    "quien ganaria",
    "le gana",
    "compara",
    "comparar",
    "comparacion",
    "stronger",
    "weaker",
    "better than",
    "who wins",
    "who would win",
    "beats",
    "compare",
    "matchup",
)
CARD_CUES = (
    "dime todo",
    "todo sobre",
    "muestrame",
    "muestra",
    "ficha",
    "ficha de",
    "carta",
    "datos de",
    "informacion",
    "info de",
    "tell me about",
    "tell me everything",
    "all about",
    "show me",
    "card",
    "profile",
    "stats of",
)
QUESTION_CUES = (
    "que ",
    "cual",
    "como",
    "cuanto",
    "cuantos",
    "donde",
    "por que",
    "cuando",
    "what",
    "which",
    "how",
    "when",
    "where",
    "why",
    "does",
    "is ",
    "are ",
    "can ",
)


class NameLookupProtocol(Protocol):
    def known_names(self) -> dict[str, int]: ...


@dataclass(frozen=True)
class ResolvedEntity:
    id: int
    name: str  # canonical database name
    matched_text: str  # what the user actually typed
    match: str  # "exact" | "fuzzy"
    score: float


@dataclass(frozen=True)
class Classification:
    intent: str
    entities: tuple[ResolvedEntity, ...]
    confidence: float
    ambiguous: bool = False  # True -> the caller may escalate to a model


def fold(text: str) -> str:
    """Lowercase, strip accents, keep letters/digits/hyphens. `Pokémon` -> `pokemon`."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch if (ch.isalnum() or ch == "-") else " " for ch in stripped)


def resolve_entities(
    text: str,
    names: dict[str, int],
    *,
    cutoff: float = 0.80,
    min_fuzzy_length: int = 4,
    limit: int = 4,
) -> tuple[ResolvedEntity, ...]:
    """Find Pokémon named in the text, tolerating misspellings.

    Exact matches are taken first and never fuzzy-checked, so genuinely short names
    (mew, muk, abra, onix) survive the length guard that protects against nonsense.
    """
    folded = fold(text)
    tokens = folded.split()
    # Adjacent pairs cover hyphenated names the user typed with a space: "mr mime".
    candidates = tokens + [f"{a}-{b}" for a, b in pairwise(tokens)]

    resolved: dict[str, ResolvedEntity] = {}
    fuzzy_pool: list[str] = []
    for candidate in candidates:
        if candidate in names:
            resolved.setdefault(
                candidate,
                ResolvedEntity(names[candidate], candidate, candidate, "exact", 1.0),
            )
        elif candidate not in STOPWORDS and len(candidate) >= min_fuzzy_length:
            fuzzy_pool.append(candidate)

    if len(resolved) < limit:
        roster = list(names)
        for candidate in fuzzy_pool:
            if len(resolved) >= limit:
                break
            close = difflib.get_close_matches(candidate, roster, n=1, cutoff=cutoff)
            if not close:
                continue
            best = close[0]
            if best in resolved:
                continue
            score = difflib.SequenceMatcher(None, candidate, best).ratio()
            resolved[best] = ResolvedEntity(names[best], best, candidate, "fuzzy", round(score, 3))

    # Order by where the user mentioned them, so "A vs B" compares A against B.
    return tuple(sorted(resolved.values(), key=lambda e: folded.find(e.matched_text)))[:limit]


def _has_cue(folded_text: str, cues: tuple[str, ...]) -> bool:
    padded = f" {folded_text} "
    return any(cue in padded for cue in cues)


def classify(text: str, entities: tuple[ResolvedEntity, ...]) -> Classification:
    """Rules in priority order; `ambiguous=True` is the only escalation trigger."""
    folded = fold(text)
    if len(entities) >= 2:
        # Two Pokémon named together is a comparison regardless of phrasing — this fires
        # before the question cues so "¿Pikachu es más fuerte que Gengar?" compares
        # instead of becoming a generic question.
        return Classification(COMPARE, entities, 0.95)
    if _has_cue(folded, COMPARE_CUES) and len(entities) == 1:
        # A comparison was clearly intended but only one side resolved; a question over
        # the retrieved corpus is the honest fallback.
        return Classification(QUESTION, entities, 0.5)
    if len(entities) == 1:
        if _has_cue(folded, CARD_CUES):
            return Classification(CARD, entities, 0.9)
        if _has_cue(folded, QUESTION_CUES):
            return Classification(QUESTION, entities, 0.9)
        remaining = [t for t in folded.split() if t not in STOPWORDS and t not in entities[0].name]
        if not remaining:
            # A bare name: "gengar", "pikachu".
            return Classification(CARD, entities, 0.95)
        return Classification(QUESTION, entities, 0.4, ambiguous=True)
    return Classification(QUESTION, entities, 0.6 if _has_cue(folded, QUESTION_CUES) else 0.3)
