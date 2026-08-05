from pokedex_common.request_id import (
    get_request_id,
    new_request_id,
    reset_request_id,
    set_request_id,
)


def test_default_is_none() -> None:
    assert get_request_id() is None


def test_set_and_reset_roundtrip() -> None:
    token = set_request_id("abc")
    assert get_request_id() == "abc"
    reset_request_id(token)
    assert get_request_id() is None


def test_new_request_id_is_unique_hex() -> None:
    first, second = new_request_id(), new_request_id()
    assert first != second
    assert len(first) == 32
    int(first, 16)  # raises if not hex
