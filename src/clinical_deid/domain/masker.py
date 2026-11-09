"""Replaces entity spans with their grouped category (FR-03)."""

from collections.abc import Iterable

from clinical_deid.domain.entities import Entity


def mask(text: str, entities: Iterable[Entity]) -> str:
    """Return ``text`` with every entity span replaced by ``[CATEGORY]``.

    Raises ``ValueError`` if a span is out of range or two spans overlap.
    """
    ordered = sorted(entities, key=lambda e: (e.start, e.end))
    previous_end = 0
    for entity in ordered:
        if not 0 <= entity.start < entity.end <= len(text):
            raise ValueError(f"Entity span out of range: {entity.start}-{entity.end}")
        if entity.start < previous_end:
            raise ValueError(f"Entity spans overlap at offset {entity.start}")
        previous_end = entity.end

    parts: list[str] = []
    cursor = 0
    for entity in ordered:
        parts.append(text[cursor : entity.start])
        parts.append(f"[{entity.category.value}]")
        cursor = entity.end
    parts.append(text[cursor:])
    return "".join(parts)
