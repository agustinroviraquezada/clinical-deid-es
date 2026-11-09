"""Domain value objects."""

from dataclasses import dataclass

from clinical_deid.domain.categories import Category


@dataclass(frozen=True, slots=True)
class Entity:
    """A detected span of personal data.

    ``start``/``end`` are character offsets (end exclusive), ``type`` is the original
    MEDDOCAN label and ``confidence`` is in [0, 1].
    """

    start: int
    end: int
    type: str
    category: Category
    text: str
    confidence: float


@dataclass(frozen=True, slots=True)
class Verdict:
    """LLM decision about an uncertain entity."""

    is_personal_data: bool
    category: Category
