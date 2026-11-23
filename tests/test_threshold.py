"""Tests for the dev-set threshold and N analysis (T3.1).

No model, torch or corpus: a fake detector and invented Spanish snippets stand in for them.
"""

import json

import pytest

from clinical_deid.adapters.fakes import FakeDetector
from clinical_deid.domain.categories import category_for
from clinical_deid.domain.entities import Entity
from modeling.evaluation.threshold import (
    ATTRIBUTION,
    DocScore,
    ScoredEntity,
    choose_n,
    choose_threshold,
    match_entities,
    percentile,
    render_markdown,
    score_documents,
    threshold_curve,
    write_report,
)


def _entity(start: int, end: int, type_: str, confidence: float, text: str = "x") -> Entity:
    return Entity(start, end, type_, category_for(type_), text, confidence)


# --- match_entities ----------------------------------------------------------


def test_match_entities_marks_exact_span_and_type_as_correct():
    gold = {(0, 5, "NOMBRE_SUJETO_ASISTENCIA")}
    pred = [_entity(0, 5, "NOMBRE_SUJETO_ASISTENCIA", 0.9)]

    assert match_entities(pred, gold) == [ScoredEntity(confidence=0.9, correct=True)]


def test_match_entities_counts_wrong_type_and_shifted_span_as_errors():
    gold = {(0, 5, "FECHAS"), (10, 15, "PAIS")}
    pred = [_entity(0, 5, "EDAD_SUJETO_ASISTENCIA", 0.4), _entity(10, 14, "PAIS", 0.6)]

    assert [e.correct for e in match_entities(pred, gold)] == [False, False]


# --- score_documents ---------------------------------------------------------


def test_score_documents_keeps_numbers_only_and_counts_gold():
    text = "Paciente Juan Pérez, 45 años."
    gold = {(9, 19, "NOMBRE_SUJETO_ASISTENCIA"), (21, 23, "EDAD_SUJETO_ASISTENCIA")}
    detector = FakeDetector([_entity(9, 19, "NOMBRE_SUJETO_ASISTENCIA", 0.99, "Juan Pérez")])

    [doc] = score_documents(detector, [("doc-1", text, gold)])

    assert doc == DocScore(doc_id="doc-1", entities=[ScoredEntity(0.99, True)], n_gold=2)
    assert "Juan" not in json.dumps(doc.to_dict())


# --- threshold_curve ---------------------------------------------------------


def _docs() -> list[DocScore]:
    # Low-confidence entities are mostly wrong; high-confidence ones are right.
    return [
        DocScore(
            "a", [ScoredEntity(0.30, False), ScoredEntity(0.55, True), ScoredEntity(0.99, True)], 3
        ),
        DocScore("b", [ScoredEntity(0.45, False), ScoredEntity(0.95, True)], 3),
        DocScore("c", [], 1),
    ]


def test_threshold_curve_splits_entities_at_each_threshold():
    curve = {row["threshold"]: row for row in threshold_curve(_docs(), [0.5, 0.9])}

    low = curve[0.5]
    assert low["n_uncertain"] == 2
    assert low["uncertain_precision"] == 0.0
    assert low["accepted_precision"] == 1.0
    assert low["accepted_recall"] == pytest.approx(3 / 7)

    high = curve[0.9]
    assert high["n_uncertain"] == 3
    assert high["uncertain_precision"] == pytest.approx(1 / 3)
    assert high["uncertain_per_doc"] == [2, 1, 0]
    # The 0.9 band only holds the entities in [0.5, 0.9): one correct (0.55).
    assert high["band_n"] == 1
    assert high["band_precision"] == 1.0
    # Model-only numbers do not depend on the threshold.
    assert high["model_precision"] == low["model_precision"] == pytest.approx(3 / 5)
    assert high["model_recall"] == pytest.approx(3 / 7)


def test_threshold_curve_reports_none_precision_for_empty_bucket():
    [row] = threshold_curve(_docs(), [0.1])

    assert row["n_uncertain"] == 0
    assert row["uncertain_precision"] is None
    assert row["band_precision"] is None


# --- choose_threshold --------------------------------------------------------


def test_choose_threshold_is_upper_edge_of_highest_unreliable_band():
    # The cumulative bucket stays below 0.85, but the [0.7, 0.9) band is reliable.
    curve = [
        {"threshold": 0.5, "band_n": 10, "band_precision": 0.40},
        {"threshold": 0.7, "band_n": 10, "band_precision": 0.80},
        {"threshold": 0.9, "band_n": 30, "band_precision": 0.90},
    ]

    assert choose_threshold(curve, max_bucket_precision=0.85) == 0.7


def test_choose_threshold_falls_back_to_lowest_t_when_model_is_reliable_everywhere():
    curve = [
        {"threshold": 0.5, "band_n": 0, "band_precision": None},
        {"threshold": 0.7, "band_n": 4, "band_precision": 0.95},
    ]

    assert choose_threshold(curve, max_bucket_precision=0.85) == 0.5


# --- percentile and N --------------------------------------------------------


def test_percentile_uses_nearest_rank():
    assert percentile([0, 0, 1, 2, 10], 50) == 1
    assert percentile([0, 0, 1, 2, 10], 95) == 10
    assert percentile([3], 90) == 3


def test_percentile_of_empty_list_is_zero():
    assert percentile([], 95) == 0


def test_choose_n_is_p95_of_uncertain_entities_per_document_and_at_least_one():
    assert choose_n([0] * 19 + [7]) == 1
    assert choose_n([1] * 18 + [4, 9]) == 4


# --- report ------------------------------------------------------------------


def test_write_report_writes_json_and_markdown_with_attribution(tmp_path):
    curve = threshold_curve(_docs(), [0.5, 0.9])
    report = {
        "split": "dev",
        "threshold": 0.5,
        "n": 2,
        "rule": "test rule",
        "curve": curve,
    }

    json_path, md_path = write_report(report, tmp_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["threshold"] == 0.5
    markdown = md_path.read_text(encoding="utf-8")
    assert ATTRIBUTION in markdown
    assert "| 0.90 |" in markdown
    assert render_markdown(report) == markdown
