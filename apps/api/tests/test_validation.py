from api.rag.context import ContextDocument
from api.rag.validation import check_type_claims


class FakeTypeLookup:
    def __init__(self, types_by_pokemon: dict[int, list[str]], known_types: list[str]) -> None:
        self._types_by_pokemon = types_by_pokemon
        self.known_types = known_types

    def types_for(self, pokemon_id: int) -> list[str] | None:
        return self._types_by_pokemon.get(pokemon_id)


KNOWN_TYPES = ["grass", "poison", "fire", "water", "electric"]


def doc(pokemon_id: int, pokemon_name: str, marker_doc_id: int) -> ContextDocument:
    return ContextDocument(
        document_id=marker_doc_id,
        title=f"{pokemon_name} card",
        content="",
        pokemon_id=pokemon_id,
        pokemon_name=pokemon_name,
        doc_type="card",
    )


def test_no_correction_when_the_claim_matches_the_real_types() -> None:
    lookup = FakeTypeLookup({1: ["grass", "poison"]}, KNOWN_TYPES)
    citation_map = {1: doc(1, "bulbasaur", 10)}

    corrections = check_type_claims(
        "Bulbasaur is a grass and poison type Pokémon [1].", citation_map, lookup
    )

    assert corrections == []


def test_matches_hyphenated_type_phrasing_from_a_real_model_response() -> None:
    # Live-caught (devlog 0029): gemini-3.6-flash answered "Grass/Poison-type" (hyphen,
    # no space before "type") for Bulbasaur — the original space-only pattern missed it
    # silently, which would have suppressed a real mismatch just as silently.
    lookup = FakeTypeLookup({1: ["grass", "poison"]}, KNOWN_TYPES)
    citation_map = {1: doc(1, "bulbasaur", 10)}

    assert (
        check_type_claims("Bulbasaur is a Grass/Poison-type Pokémon [1].", citation_map, lookup)
        == []
    )
    corrections = check_type_claims(
        "Bulbasaur is a Fire/Poison-type Pokémon [1].", citation_map, lookup
    )
    assert corrections[0].claimed_types == ["fire", "poison"]


def test_correction_when_the_claim_contradicts_the_real_types() -> None:
    lookup = FakeTypeLookup({7: ["water"]}, KNOWN_TYPES)
    citation_map = {1: doc(7, "squirtle", 20)}

    corrections = check_type_claims("Squirtle is a fire type Pokémon [1].", citation_map, lookup)

    assert len(corrections) == 1
    correction = corrections[0]
    assert correction.pokemon_name == "squirtle"
    assert correction.claimed_types == ["fire"]
    assert correction.actual_types == ["water"]
    assert correction.note() == "Correction: squirtle is water type, not fire."


def test_no_type_claim_in_the_answer_is_a_no_op() -> None:
    lookup = FakeTypeLookup({7: ["water"]}, KNOWN_TYPES)
    citation_map = {1: doc(7, "squirtle", 20)}

    assert check_type_claims("Squirtle likes to swim [1].", citation_map, lookup) == []


def test_multiple_cited_pokemon_are_ambiguous_and_skipped() -> None:
    lookup = FakeTypeLookup({1: ["grass", "poison"], 7: ["water"]}, KNOWN_TYPES)
    citation_map = {1: doc(1, "bulbasaur", 10), 2: doc(7, "squirtle", 20)}

    corrections = check_type_claims(
        "Bulbasaur is a fire type Pokémon [1], unlike Squirtle [2].", citation_map, lookup
    )

    assert corrections == []


def test_unknown_pokemon_id_is_a_no_op() -> None:
    lookup = FakeTypeLookup({}, KNOWN_TYPES)
    citation_map = {1: doc(999, "missingno", 10)}

    assert check_type_claims("Missingno is a water type [1].", citation_map, lookup) == []


def test_empty_known_types_is_a_no_op() -> None:
    lookup = FakeTypeLookup({7: ["water"]}, [])
    citation_map = {1: doc(7, "squirtle", 20)}

    assert check_type_claims("Squirtle is a fire type [1].", citation_map, lookup) == []
