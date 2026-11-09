"""Cascade use case: detect -> filter uncertain -> verify -> mask (design §3).

Skeleton (T1.3): uncertain entities are masked by default without calling the LLM, which is
the conservative outcome. LLM verification, the N cap and the fail-safe are wired in T3.3.
"""

from dataclasses import dataclass

from clinical_deid.domain.entities import Entity
from clinical_deid.domain.masker import mask
from clinical_deid.ports import EntityDetector, LLMVerifier


@dataclass(frozen=True, slots=True)
class CascadeResult:
    """Output of one cascade run."""

    deidentified_text: str
    entities: list[Entity]
    n_llm: int


class Cascade:
    """Orchestrates the detector, the LLM verifier and the masker."""

    def __init__(self, detector: EntityDetector, verifier: LLMVerifier, threshold: float) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        self._detector = detector
        self._verifier = verifier
        self._threshold = threshold

    def run(self, text: str) -> CascadeResult:
        """De-identify ``text``."""
        detected = self._detector.detect(text)
        confident = [e for e in detected if e.confidence >= self._threshold]
        uncertain = [e for e in detected if e.confidence < self._threshold]
        # T1.3: uncertain entities are kept (masked) without LLM verification.
        accepted = confident + uncertain
        return CascadeResult(
            deidentified_text=mask(text, accepted),
            entities=sorted(accepted, key=lambda e: e.start),
            n_llm=0,
        )
