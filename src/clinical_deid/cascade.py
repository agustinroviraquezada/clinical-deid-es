"""Cascade use case: detect -> filter uncertain -> verify -> mask (design §3, ADR-0004).

Confident entities are accepted. Uncertain ones are verified by the LLM, sending only their
sentence (FR-06, at most ``MAX_LLM_SENTENCE_CHARS``), at most ``max_llm_calls`` times per
document (FR-07) and, optionally, within a total time budget (LLM10). Anything not verified —
beyond the cap, past the budget, an oversized sentence or any failure (segmentation, verifier
error, malformed verdict) — is masked (fail-safe). Nothing here logs text, sentences or verdicts.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from clinical_deid.domain.categories import Category
from clinical_deid.domain.entities import Entity, Verdict
from clinical_deid.domain.masker import mask
from clinical_deid.domain.sentences import sentence_bounds
from clinical_deid.ports import EntityDetector, LLMVerifier

DEFAULT_MAX_LLM_CALLS = 8  # ADR-0009
# FR-06 guard: a longer "sentence" means segmentation failed and would leak the document.
MAX_LLM_SENTENCE_CHARS = 1_000


@dataclass(frozen=True, slots=True)
class CascadeResult:
    """Output of one cascade run.

    ``llm_verified`` holds the ``(start, end)`` spans whose masking the LLM confirmed;
    ``n_llm`` counts verifier calls attempted, failed ones included (they still cost).
    """

    deidentified_text: str
    entities: list[Entity]
    n_llm: int
    llm_verified: frozenset[tuple[int, int]] = frozenset()


class Cascade:
    """Orchestrates the detector, the LLM verifier and the masker."""

    def __init__(
        self,
        detector: EntityDetector,
        verifier: LLMVerifier,
        threshold: float,
        max_llm_calls: int = DEFAULT_MAX_LLM_CALLS,
        llm_time_budget_s: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be in [0, 1]")
        if max_llm_calls < 0:
            raise ValueError("max_llm_calls must be >= 0")
        if llm_time_budget_s is not None and llm_time_budget_s <= 0:
            raise ValueError("llm_time_budget_s must be > 0")
        self._detector = detector
        self._verifier = verifier
        self._threshold = threshold
        self._max_llm_calls = max_llm_calls
        self._budget = llm_time_budget_s
        self._clock = clock

    def run(self, text: str) -> CascadeResult:
        """De-identify ``text``."""
        detected = self._detector.detect(text)
        accepted = [e for e in detected if e.confidence >= self._threshold]
        uncertain = sorted(
            (e for e in detected if e.confidence < self._threshold), key=lambda e: e.start
        )

        verified: set[tuple[int, int]] = set()
        n_llm = 0
        started = self._clock()
        for entity in uncertain:
            if n_llm >= self._max_llm_calls or self._budget_exhausted(started):
                accepted.append(entity)  # FR-07: beyond the cap, masked by default.
                continue
            try:
                begin, end = sentence_bounds(text, entity.start, entity.end)
                if end - begin > MAX_LLM_SENTENCE_CHARS:
                    accepted.append(entity)  # FR-06: never send an oversized fragment.
                    continue
                n_llm += 1
                verdict = self._verifier.verify(text[begin:end], entity)
                if not (
                    isinstance(verdict, Verdict)
                    and isinstance(verdict.is_personal_data, bool)
                    and isinstance(verdict.category, Category)
                ):
                    raise TypeError("Malformed verdict")
            except Exception:  # noqa: BLE001 — fail-safe: any failure masks the entity.
                accepted.append(entity)
                continue
            if verdict.is_personal_data:
                accepted.append(replace(entity, category=verdict.category))
                verified.add((entity.start, entity.end))

        return CascadeResult(
            deidentified_text=mask(text, accepted),
            entities=sorted(accepted, key=lambda e: e.start),
            n_llm=n_llm,
            llm_verified=frozenset(verified),
        )

    def _budget_exhausted(self, started: float) -> bool:
        return self._budget is not None and self._clock() - started >= self._budget
