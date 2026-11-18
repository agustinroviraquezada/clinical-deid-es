"""EntityDetector backed by the fine-tuned Hugging Face token-classification model (FR-02).

``transformers`` and ``torch`` are imported only in :meth:`HFEntityDetector.from_pretrained`, so
the mapping logic can be tested with a fake pipeline and no model.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from clinical_deid.domain.categories import category_for
from clinical_deid.domain.entities import Entity

# A token-classification pipeline: text in, aggregated spans out. Each span has
# ``entity_group`` (MEDDOCAN label), ``score``, ``start`` and ``end`` (character offsets).
TokenClassifier = Callable[[str], Sequence[Mapping[str, Any]]]

# RoBERTa has 514 positions; 512 tokens per window, overlapping by STRIDE tokens so an entity cut
# by a window border is seen whole in the next one.
MAX_LENGTH = 512
STRIDE = 128


@dataclass(slots=True)
class _Span:
    start: int
    end: int
    label: str
    score: float


class HFEntityDetector:
    """Detects personal data with a token-classification pipeline."""

    def __init__(self, classifier: TokenClassifier) -> None:
        self._classifier = classifier

    @classmethod
    def from_pretrained(cls, model_path: str | Path) -> HFEntityDetector:
        """Load the model and tokenizer from a local folder (CPU only, no network)."""
        from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline

        # add_prefix_space matches training, where the text was split into words.
        tokenizer = AutoTokenizer.from_pretrained(
            model_path, add_prefix_space=True, model_max_length=MAX_LENGTH
        )
        model = AutoModelForTokenClassification.from_pretrained(model_path)
        classifier = pipeline(
            "token-classification",
            model=model,
            tokenizer=tokenizer,
            aggregation_strategy="first",
            stride=STRIDE,
            device=-1,
        )
        return cls(classifier)

    def detect(self, text: str) -> list[Entity]:
        """Return non-overlapping entities sorted by offset, confidence in [0, 1]."""
        if not text.strip():
            return []
        spans = [s for s in (_trimmed(text, raw) for raw in self._classifier(text)) if s]
        return [
            Entity(
                start=s.start,
                end=s.end,
                type=s.label,
                category=category_for(s.label),
                text=text[s.start : s.end],
                confidence=s.score,
            )
            for s in _merge_overlaps(spans)
        ]


def _trimmed(text: str, raw: Mapping[str, Any]) -> _Span | None:
    """Span without surrounding whitespace; ``None`` if nothing is left."""
    start, end = int(raw["start"]), int(raw["end"])
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    if start >= end:
        return None
    score = min(max(float(raw["score"]), 0.0), 1.0)
    return _Span(start, end, str(raw["entity_group"]), score)


def _merge_overlaps(spans: list[_Span]) -> list[_Span]:
    """Join overlapping spans into their union so nothing is left unmasked.

    Overlaps come from the overlapping windows used on long notes. The merged span keeps the
    label and score of its most confident part.
    """
    merged: list[_Span] = []
    for span in sorted(spans, key=lambda s: (s.start, s.end)):
        last = merged[-1] if merged else None
        if last is None or span.start >= last.end:
            merged.append(span)
            continue
        last.end = max(last.end, span.end)
        if span.score > last.score:
            last.label, last.score = span.label, span.score
    return merged
