"""Intent classification: rules, fuzzy names, escalation and failure degradation."""

import pytest

from api.intent import FakeIntentClassifier, IntentService
from api.intent.classifier import ClassifierVerdict, IntentParsingError, LLMIntentClassifier
from api.intent.rules import classify, resolve_entities
from pokedex_llm import FakeLLM, TransientProviderError

# A representative slice of the roster: short names, hyphenated names, lookalikes.
NAMES = {
    "bulbasaur": 1,
    "ivysaur": 2,
    "charizard": 6,
    "squirtle": 7,
    "pikachu": 25,
    "raichu": 26,
    "paras": 46,
    "mew": 151,
    "mewtwo": 150,
    "abra": 63,
    "onix": 95,
    "gengar": 94,
    "mr-mime": 122,
    "jigglypuff": 39,
    "spearow": 21,
    "kabuto": 140,
    "dragonite": 149,
}


class FakeNameLookup:
    def known_names(self) -> dict[str, int]:
        return NAMES


def service(classifier=None) -> IntentService:
    return IntentService(FakeNameLookup(), classifier)


# --- entity resolution --------------------------------------------------------------


def test_exact_names_resolve_regardless_of_case_and_accents() -> None:
    entities = resolve_entities("Dime todo sobre GENGAR", NAMES)

    assert [e.name for e in entities] == ["gengar"]
    assert entities[0].match == "exact"


def test_misspellings_resolve_by_fuzzy_match() -> None:
    for typo, expected in [
        ("pickachu", "pikachu"),
        ("charizrd", "charizard"),
        ("bulbasur", "bulbasaur"),
        ("squirtel", "squirtle"),
        ("jiglypuff", "jigglypuff"),
        ("dragonight", "dragonite"),
    ]:
        entities = resolve_entities(f"tell me about {typo}", NAMES)
        assert [e.name for e in entities] == [expected], typo
        assert entities[0].match == "fuzzy"


@pytest.mark.parametrize(
    "word", ["para", "pero", "sobre", "todo", "dime", "me", "about", "entre", "contra"]
)
def test_spanish_and_english_stopwords_never_resolve_to_pokemon(word) -> None:
    """Measured hazard: 'para' scores 0.889 against 'paras', which clears any usable
    fuzzy cutoff. Without the stopword list, ordinary Spanish sentences sprout
    phantom entities and mis-route."""
    assert resolve_entities(f"cual es mejor {word} atacar", NAMES) == ()


def test_short_real_names_survive_but_short_typos_do_not() -> None:
    assert [e.name for e in resolve_entities("show me mew", NAMES)] == ["mew"]
    # "mw" is too short for fuzzy matching — silence beats a guess.
    assert resolve_entities("show me mw", NAMES) == ()


def test_hyphenated_names_match_when_typed_with_a_space() -> None:
    assert [e.name for e in resolve_entities("mr mime card", NAMES)] == ["mr-mime"]


def test_entities_keep_the_order_the_user_wrote() -> None:
    entities = resolve_entities("gengar vs pikachu", NAMES)

    assert [e.name for e in entities] == ["gengar", "pikachu"]


def test_lookalike_names_resolve_to_themselves() -> None:
    """raichu must not swallow pikachu or vice versa."""
    entities = resolve_entities("pikachu o raichu?", NAMES)

    assert {e.name for e in entities} == {"pikachu", "raichu"}


# --- the user's real queries, verbatim ------------------------------------------------


def test_the_users_own_examples_take_the_free_path() -> None:
    cases = [
        ("Pickachu es mas fuerte que Gengar?", "compare", ["pikachu", "gengar"]),
        ("Dime todo sobre Gengar", "card", ["gengar"]),
        ("what type is Bulbasaur?", "question", ["bulbasaur"]),
    ]
    for text, expected_intent, expected_entities in cases:
        result = service().resolve(text)
        assert result.intent == expected_intent, text
        assert [e.name for e in result.entities] == expected_entities, text
        assert result.method == "deterministic", text


# --- rule classification --------------------------------------------------------------


def test_a_bare_name_is_a_card_request() -> None:
    result = service().resolve("gengar")

    assert (result.intent, result.method) == ("card", "deterministic")


def test_two_names_compare_even_phrased_as_a_question() -> None:
    result = service().resolve("¿quién gana entre Mewtwo y Mew?")

    assert result.intent == "compare"
    assert {e.name for e in result.entities} == {"mewtwo", "mew"}


def test_a_comparison_cue_with_one_resolved_name_degrades_to_question() -> None:
    entities = resolve_entities("pikachu vs digimon", NAMES)
    ruled = classify("pikachu vs digimon", entities)

    assert ruled.intent == "question"
    assert not ruled.ambiguous  # honest degrade, not an escalation


def test_no_entities_is_a_question() -> None:
    result = service().resolve("which starter is best?")

    assert (result.intent, result.method) == ("question", "deterministic")


# --- escalation and failure -----------------------------------------------------------


AMBIGUOUS = "gengar sombra nocturna daño"  # 1 entity + unknown content words, no cue


def test_ambiguous_input_escalates_when_a_classifier_exists() -> None:
    classifier = FakeIntentClassifier(script=[ClassifierVerdict("card", (), "wants the entry")])

    result = service(classifier).resolve(AMBIGUOUS)

    assert (result.intent, result.method) == ("card", "llm")
    assert classifier.calls and classifier.calls[0][1] == ("gengar",)


def test_without_a_classifier_ambiguity_degrades_to_question() -> None:
    result = service(None).resolve(AMBIGUOUS)

    assert (result.intent, result.method) == ("question", "deterministic")


def test_a_broken_classifier_degrades_to_question_never_raises() -> None:
    classifier = FakeIntentClassifier(script=[TransientProviderError("503 upstream")])

    result = service(classifier).resolve(AMBIGUOUS)

    assert (result.intent, result.method) == ("question", "fallback")
    assert any("classifier failed" in w for w in result.warnings)


def test_clear_input_never_touches_the_classifier() -> None:
    """The cost property: /intent is hit on every submission, so the free path must
    answer everything unambiguous without a model call."""
    classifier = FakeIntentClassifier()

    service(classifier).resolve("Dime todo sobre Gengar")
    service(classifier).resolve("pikachu vs gengar")

    assert classifier.calls == []


def test_the_classifier_may_add_only_names_that_resolve() -> None:
    """The model can rescue a name the rules missed, but an invented Pokémon is dropped
    at re-resolution — the classifier cannot mint entities."""
    classifier = FakeIntentClassifier(
        script=[ClassifierVerdict("compare", ("mewtwo", "agumon"), "sees two")]
    )

    result = service(classifier).resolve(AMBIGUOUS)

    # gengar (from rules) + mewtwo (classifier, resolves) but never agumon.
    assert {e.name for e in result.entities} == {"gengar", "mewtwo"}
    assert result.intent == "compare"


def test_an_unknown_intent_label_degrades_to_question() -> None:
    classifier = FakeIntentClassifier(script=[ClassifierVerdict("battle", (), "?")])

    result = service(classifier).resolve(AMBIGUOUS)

    assert result.intent == "question"
    assert any("unknown intent" in w for w in result.warnings)


def test_compare_verdict_without_two_entities_degrades_to_question() -> None:
    classifier = FakeIntentClassifier(script=[ClassifierVerdict("compare", (), "compare!")])

    result = service(classifier).resolve(AMBIGUOUS)

    assert result.intent == "question"


# --- the LLM classifier itself ---------------------------------------------------------


def test_llm_classifier_requests_structured_json_at_temperature_zero() -> None:
    llm = FakeLLM(script=['{"intent": "card", "pokemon": ["gengar"], "reasoning": "ok"}'])

    verdict = LLMIntentClassifier(llm).classify("gengar sombra", ("gengar",))

    assert verdict.intent == "card"
    request = llm.requests[0]
    assert request.temperature == 0.0
    assert request.response_mime_type == "application/json"


def test_llm_classifier_raises_a_typed_error_on_garbage() -> None:
    llm = FakeLLM(script=["not json at all"])

    with pytest.raises(IntentParsingError):
        LLMIntentClassifier(llm).classify("whatever", ())
