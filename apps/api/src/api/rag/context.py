"""Context builder: numbered documents under a size budget, with a citation map.

The budget is character-based (≈4 chars/token) — boring and deterministic. Documents
enter in rank order; one document always fits (truncated if oversized) so the model
never receives an empty context when retrieval produced hits.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ContextDocument:
    document_id: int
    title: str
    content: str
    pokemon_id: int
    pokemon_name: str
    doc_type: str
    source_refs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class BuiltContext:
    text: str
    citation_map: dict[int, ContextDocument]  # marker -> document

    @property
    def markers(self) -> list[int]:
        return sorted(self.citation_map)


def build_context(documents: list[ContextDocument], budget_chars: int = 12_000) -> BuiltContext:
    if budget_chars < 200:
        raise ValueError(f"budget_chars too small to be useful: {budget_chars}")
    blocks: list[str] = []
    citation_map: dict[int, ContextDocument] = {}
    used = 0
    for document in documents:
        marker = len(citation_map) + 1
        block = f"[{marker}] {document.title}\n{document.content}"
        if used + len(block) > budget_chars:
            if not citation_map:  # always include at least one document, truncated
                block = block[: budget_chars - 1] + "…"
            else:
                break
        blocks.append(block)
        citation_map[marker] = document
        used += len(block)
    return BuiltContext(text="\n\n".join(blocks), citation_map=citation_map)
