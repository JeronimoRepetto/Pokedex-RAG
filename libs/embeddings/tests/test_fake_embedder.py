import math

from pokedex_embeddings import FakeEmbedder


def norm(vector: list[float]) -> float:
    return math.sqrt(sum(v * v for v in vector))


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_same_input_gives_same_unit_vector() -> None:
    embedder = FakeEmbedder()

    first = embedder.embed_texts(["pikachu"])[0]
    second = embedder.embed_texts(["pikachu"])[0]

    assert first == second
    assert len(first) == 768
    assert abs(norm(first) - 1.0) < 1e-9


def test_different_inputs_give_different_vectors() -> None:
    embedder = FakeEmbedder()

    a, b = embedder.embed_texts(["pikachu", "charmander"])

    assert abs(cosine(a, b)) < 0.5  # sha256-seeded vectors are near-orthogonal


def test_query_embedding_matches_document_embedding_of_the_same_text() -> None:
    """Search tests build exact matches by embedding the same text on both sides —
    embed_query must stay consistent with embed_texts for that to keep working."""
    embedder = FakeEmbedder(dimensions=64)

    assert embedder.embed_query("pikachu") == embedder.embed_texts(["pikachu"])[0]


def test_image_embedding_is_deterministic_and_distinct_from_text() -> None:
    embedder = FakeEmbedder(dimensions=64)

    image = embedder.embed_image(b"\x89PNG-bytes", "image/png")

    assert image == embedder.embed_image(b"\x89PNG-bytes", "image/png")
    assert len(image) == 64
    assert image != embedder.embed_texts(["\x89PNG-bytes"])[0]
