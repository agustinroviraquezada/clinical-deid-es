"""Synthetic demo notes and their precomputed results (FR-12, task T4.4).

No model: a fake detector stands in for it. The committed report is checked against the
examples so it cannot silently go stale.
"""

import json

import pytest

from clinical_deid.adapters.fakes import FakeDetector
from clinical_deid.api.app import REPORT_DIR, STATIC_DIR
from clinical_deid.domain.categories import MEDDOCAN_TO_CATEGORY, category_for
from clinical_deid.domain.entities import Entity
from modeling.evaluation.synthetic import (
    DEFAULT_GOLD,
    REPORT_NAME,
    build_report,
    gold_spans,
    load_synthetic,
    text_digest,
)

EXAMPLES = json.loads((STATIC_DIR / "examples.json").read_text(encoding="utf-8"))
SYNTHETIC = [e for e in EXAMPLES if e["source"] == "synthetic"]
GOLD = json.loads(DEFAULT_GOLD.read_text(encoding="utf-8"))


def test_gold_spans_find_every_whole_word_occurrence():
    text = "Ana vio a Ana. Mariana no."

    spans = gold_spans(text, [["Ana", "NOMBRE_SUJETO_ASISTENCIA"]])

    assert spans == {(0, 3, "NOMBRE_SUJETO_ASISTENCIA"), (10, 13, "NOMBRE_SUJETO_ASISTENCIA")}


def test_gold_spans_refuse_a_surface_missing_from_the_text():
    with pytest.raises(ValueError, match="not found"):
        gold_spans("Paciente sin datos.", [["Lucía", "NOMBRE_SUJETO_ASISTENCIA"]])


def test_gold_spans_refuse_overlapping_entities():
    with pytest.raises(ValueError, match="overlap"):
        gold_spans("Calle Mayor 3", [["Calle Mayor 3", "CALLE"], ["Mayor", "TERRITORIO"]])


def test_at_least_five_synthetic_notes_in_distinct_styles():
    assert len(SYNTHETIC) >= 5
    styles = [GOLD[e["id"]]["style"] for e in SYNTHETIC]
    assert len(set(styles)) == len(styles)
    assert {"progress note", "abbreviations", "discharge report"} <= set(styles)


@pytest.mark.parametrize("example", SYNTHETIC, ids=lambda e: e["id"])
def test_every_synthetic_note_has_valid_gold(example):
    entities = GOLD[example["id"]]["entities"]

    assert entities
    assert all(type_ in MEDDOCAN_TO_CATEGORY for _, type_ in entities)
    spans = gold_spans(example["text"], entities)  # raises if missing or overlapping
    assert all(0 <= s < e <= len(example["text"]) for s, e, _ in spans)


def test_gold_has_no_entry_without_a_note():
    ids = {e["id"] for e in SYNTHETIC}
    assert set(GOLD) - {"_about"} == ids


def test_build_report_scores_model_only_and_leaves_llm_configurations_pending():
    text = "Paciente Juan Pérez, 54 años."
    note = {"id": "n1", "title": "T", "source": "synthetic", "text": text}
    gold = {
        "n1": {
            "style": "progress note",
            "entities": [
                ["Juan Pérez", "NOMBRE_SUJETO_ASISTENCIA"],
                ["54 años", "EDAD_SUJETO_ASISTENCIA"],
            ],
        }
    }
    found = Entity(
        9,
        19,
        "NOMBRE_SUJETO_ASISTENCIA",
        category_for("NOMBRE_SUJETO_ASISTENCIA"),
        "Juan Pérez",
        0.90,
    )

    report = build_report(
        load_synthetic([note], gold), FakeDetector([found]).detect, threshold=0.96
    )

    [row] = report["examples"]
    model = row["configurations"]["model_only"]
    assert model["status"] == "done"
    assert model["masked"] == "Paciente [NAME], 54 años."
    assert (model["tp"], model["fp"], model["fn"]) == (1, 0, 1)
    assert model["n_uncertain"] == 1  # 0.90 < 0.96: the cascade would ask the LLM
    assert model["missed"] == [{"start": 21, "end": 28, "category": "AGE"}]
    assert row["configurations"]["cascade"] == {"status": "pending"}
    assert row["configurations"]["llm_only"] == {"status": "pending"}
    assert row["text_sha256"] == text_digest(note["text"])
    assert report["overall"]["model_only"]["recall"] == 0.5
    assert "synthetic" in report["about"].lower()


def test_committed_report_covers_every_synthetic_note_and_is_current():
    report = json.loads((REPORT_DIR / f"{REPORT_NAME}.json").read_text(encoding="utf-8"))
    rows = {row["id"]: row for row in report["examples"]}

    assert set(rows) == {e["id"] for e in SYNTHETIC}
    for example in SYNTHETIC:
        row = rows[example["id"]]
        assert row["text_sha256"] == text_digest(example["text"]), "re-run the precompute script"
        assert row["configurations"]["model_only"]["status"] == "done"
