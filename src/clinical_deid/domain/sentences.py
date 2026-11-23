"""Sentence segmentation for the LLM fragment (FR-06, design §3).

Rule-based on purpose: no model, no dependency. A boundary is whitespace after ``.``, ``!``
or ``?``, or any line break. Abbreviations such as "Dr." produce a shorter fragment, which is
the conservative side for FR-06 (less text leaves the system).
"""

import re

_BOUNDARY = re.compile(r"(?<=[.!?])\s+|\s*\n\s*")


def sentence_bounds(text: str, start: int, end: int) -> tuple[int, int]:
    """Return ``(begin, end)`` of the sentence that contains the span ``text[start:end]``.

    Boundaries inside the span are ignored, so the sentence always contains the whole span.
    Raises ``ValueError`` if the span is empty or out of range.
    """
    if not 0 <= start < end <= len(text):
        raise ValueError(f"Span out of range: {start}-{end}")

    begin = 0
    for match in _BOUNDARY.finditer(text, 0, start):
        begin = match.end()
    after = _BOUNDARY.search(text, end)
    return begin, after.start() if after else len(text)
