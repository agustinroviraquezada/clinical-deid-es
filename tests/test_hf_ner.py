"""HFEntityDetector turns token-classification spans into domain entities (FR-02).

Unit tests inject a fake pipeline: no model is downloaded or loaded.
"""

import os
from pathlib import Path

import pytest

from clinical_deid.adapters.hf_ner import HFEntityDetector
from clinical_deid.domain.categories import Category
from clinical_deid.domain.masker import mask

NOTE = "Paciente Lucía Fernández, de 54 años, ingresó el 12/03/2025 en Teruel."


def _span(fragment: str, label: str, score: float, text: str = NOTE) -> dict:
    start = text.index(fragment)
    return {
        "entity_group": label,
        "score": score,
        "word": fragment,
        "start": start,
        "end": start + len(fragment),
    }


class FakePipeline:
    """Stands in for ``transformers.pipeline("token-classification")``."""

    def __init__(self, spans: list[dict]) -> None:
        self._spans = spans
        self.calls: list[str] = []

    def __call__(self, text: str) -> list[dict]:
        self.calls.append(text)
        return list(self._spans)


def test_spans_become_entities_with_category_and_confidence():
    pipe = FakePipeline(
        [
            _span("Lucía Fernández", "NOMBRE_SUJETO_ASISTENCIA", 0.99),
            _span("12/03/2025", "FECHAS", 0.75),
        ]
    )

    entities = HFEntityDetector(pipe).detect(NOTE)

    assert [(e.text, e.type, e.category, e.confidence) for e in entities] == [
        ("Lucía Fernández", "NOMBRE_SUJETO_ASISTENCIA", Category.NAME, 0.99),
        ("12/03/2025", "FECHAS", Category.DATE, 0.75),
    ]
    assert all(NOTE[e.start : e.end] == e.text for e in entities)


def test_entities_are_sorted_by_offset():
    pipe = FakePipeline(
        [_span("Teruel", "TERRITORIO", 0.9), _span("54 años", "EDAD_SUJETO_ASISTENCIA", 0.9)]
    )

    entities = HFEntityDetector(pipe).detect(NOTE)

    assert [e.text for e in entities] == ["54 años", "Teruel"]


def test_unknown_label_falls_back_to_other_and_is_still_returned():
    pipe = FakePipeline([_span("Teruel", "SOMETHING_NEW", 0.9)])

    (entity,) = HFEntityDetector(pipe).detect(NOTE)

    assert entity.category is Category.OTHER


def test_surrounding_whitespace_is_trimmed_from_spans():
    start = NOTE.index(" Teruel")
    pipe = FakePipeline(
        [{"entity_group": "TERRITORIO", "score": 0.9, "start": start, "end": start + 7}]
    )

    (entity,) = HFEntityDetector(pipe).detect(NOTE)

    assert entity.text == "Teruel"
    assert NOTE[entity.start : entity.end] == "Teruel"


def test_blank_or_empty_spans_are_dropped():
    start = NOTE.index(", de")
    pipe = FakePipeline(
        [
            {"entity_group": "OTROS_SUJETO_ASISTENCIA", "score": 0.9, "start": 3, "end": 3},
            {
                "entity_group": "OTROS_SUJETO_ASISTENCIA",
                "score": 0.9,
                "start": start + 1,
                "end": start + 2,
            },
        ]
    )

    assert HFEntityDetector(pipe).detect(NOTE) == []


def test_overlapping_spans_are_merged_so_masking_never_fails():
    """Windowed inference can return the same entity twice with different boundaries."""
    pipe = FakePipeline(
        [
            _span("Lucía", "NOMBRE_SUJETO_ASISTENCIA", 0.6),
            _span("Lucía Fernández", "NOMBRE_SUJETO_ASISTENCIA", 0.95),
            _span("Fernández, de 54", "EDAD_SUJETO_ASISTENCIA", 0.5),
        ]
    )

    entities = HFEntityDetector(pipe).detect(NOTE)

    (merged,) = entities
    assert merged.text == "Lucía Fernández, de 54"  # union: nothing is left unmasked
    assert merged.type == "NOMBRE_SUJETO_ASISTENCIA"  # label of the most confident span
    assert merged.confidence == 0.95
    assert mask(NOTE, entities).startswith("Paciente [NAME] años")


def test_scores_are_plain_floats_in_unit_interval():
    class NumpyLikeScore(float):
        """numpy.float32 is a float subclass; the entity must hold a plain float."""

    pipe = FakePipeline([_span("Teruel", "TERRITORIO", NumpyLikeScore(1.0000001))])

    (entity,) = HFEntityDetector(pipe).detect(NOTE)

    assert type(entity.confidence) is float
    assert entity.confidence == 1.0


def test_empty_text_does_not_call_the_model():
    pipe = FakePipeline([])

    assert HFEntityDetector(pipe).detect("") == []
    assert HFEntityDetector(pipe).detect("   \n") == []
    assert pipe.calls == []


@pytest.mark.integration
def test_real_model_masks_a_synthetic_note():
    """Needs the published model on disk: MODEL_PATH=<folder> uv run pytest -m integration."""
    model_path = Path(os.environ.get("MODEL_PATH", "model"))
    if not (model_path / "config.json").exists():
        pytest.skip(f"no model at {model_path}")
    detector = HFEntityDetector.from_pretrained(model_path)

    entities = detector.detect(NOTE)

    masked = mask(NOTE, entities)
    assert "Lucía" not in masked
    assert "12/03/2025" not in masked
    assert "[NAME]" in masked
