"""Tests for the pure helpers of the model-only evaluation (T2.4).

They need neither torch nor transformers nor the model: inference itself runs on demand.
Tag sequences are synthetic; no corpus text is used.
"""

import json

import pytest

from clinical_deid.domain.categories import MEDDOCAN_TO_CATEGORY, Category
from modeling.evaluation.evaluate import (
    bio_to_spans,
    first_subtoken_tags,
    render_markdown,
    score,
    write_report,
)

# --- bio_to_spans ------------------------------------------------------------


def test_bio_to_spans_extracts_typed_spans_with_exclusive_end():
    tags = ["O", "B-FECHAS", "I-FECHAS", "O", "B-PAIS"]

    assert bio_to_spans(tags) == {(1, 3, "FECHAS"), (4, 5, "PAIS")}


def test_bio_to_spans_closes_entity_at_end_of_sentence():
    assert bio_to_spans(["B-CALLE", "I-CALLE", "I-CALLE"]) == {(0, 3, "CALLE")}


def test_bio_to_spans_treats_orphan_inside_tag_as_entity_start():
    # Same convention as seqeval's default mode, so results match the training metrics.
    assert bio_to_spans(["O", "I-HOSPITAL", "I-HOSPITAL"]) == {(1, 3, "HOSPITAL")}


def test_bio_to_spans_splits_on_type_change_inside_entity():
    tags = ["B-TERRITORIO", "I-TERRITORIO", "I-PAIS"]

    assert bio_to_spans(tags) == {(0, 2, "TERRITORIO"), (2, 3, "PAIS")}


def test_bio_to_spans_splits_adjacent_entities_of_same_type():
    tags = ["B-FECHAS", "B-FECHAS", "I-FECHAS"]

    assert bio_to_spans(tags) == {(0, 1, "FECHAS"), (1, 3, "FECHAS")}


def test_bio_to_spans_of_sentence_without_entities_is_empty():
    assert bio_to_spans(["O", "O"]) == set()
    assert bio_to_spans([]) == set()


# --- score -------------------------------------------------------------------


def test_score_perfect_prediction_gives_ones():
    gold = [["B-FECHAS", "I-FECHAS", "O"], ["B-PAIS"]]

    result = score(gold, gold)

    assert result["overall"] == {
        "precision": 1.0,
        "recall": 1.0,
        "f1": 1.0,
        "support": 2,
        "tp": 2,
        "fp": 0,
        "fn": 0,
    }


def test_score_computes_micro_metrics_by_hand():
    gold = [["B-FECHAS", "I-FECHAS", "O", "B-PAIS"], ["B-CALLE", "O"]]
    pred = [["B-FECHAS", "I-FECHAS", "O", "O"], ["B-CALLE", "B-PAIS"]]
    # tp = FECHAS + CALLE = 2, fn = PAIS (sentence 0) = 1, fp = PAIS (sentence 1) = 1

    overall = score(gold, pred)["overall"]

    assert (overall["tp"], overall["fp"], overall["fn"]) == (2, 1, 1)
    assert overall["precision"] == pytest.approx(2 / 3)
    assert overall["recall"] == pytest.approx(2 / 3)
    assert overall["f1"] == pytest.approx(2 / 3)
    assert overall["support"] == 3


def test_score_requires_exact_span_boundaries():
    gold = [["B-CALLE", "I-CALLE", "I-CALLE"]]
    pred = [["B-CALLE", "I-CALLE", "O"]]

    overall = score(gold, pred)["overall"]

    assert (overall["tp"], overall["fp"], overall["fn"]) == (0, 1, 1)


def test_score_wrong_type_counts_as_false_positive_and_false_negative():
    gold = [["B-NOMBRE_SUJETO_ASISTENCIA"]]
    pred = [["B-NOMBRE_PERSONAL_SANITARIO"]]

    result = score(gold, pred)

    assert result["overall"]["recall"] == 0.0
    assert result["per_type"]["NOMBRE_SUJETO_ASISTENCIA"]["fn"] == 1
    assert result["per_type"]["NOMBRE_PERSONAL_SANITARIO"]["fp"] == 1


def test_score_does_not_match_spans_across_sentences():
    gold = [["B-PAIS"], ["O"]]
    pred = [["O"], ["B-PAIS"]]

    overall = score(gold, pred)["overall"]

    assert (overall["tp"], overall["fp"], overall["fn"]) == (0, 1, 1)


def test_score_without_entities_gives_zeros_not_division_error():
    result = score([["O", "O"]], [["O", "O"]])

    assert result["overall"]["precision"] == 0.0
    assert result["overall"]["recall"] == 0.0
    assert result["overall"]["f1"] == 0.0


def test_score_lists_every_meddocan_type_even_without_support():
    # ID_EMPLEO_PERSONAL_SANITARIO has no example in test (T2.1 stats).
    result = score([["B-FECHAS"]], [["B-FECHAS"]])

    assert set(result["per_type"]) == set(MEDDOCAN_TO_CATEGORY)
    assert result["per_type"]["ID_EMPLEO_PERSONAL_SANITARIO"]["support"] == 0


def test_score_aggregates_types_into_product_categories():
    gold = [["B-NOMBRE_SUJETO_ASISTENCIA", "B-NOMBRE_PERSONAL_SANITARIO", "B-FECHAS"]]
    pred = [["B-NOMBRE_SUJETO_ASISTENCIA", "O", "B-FECHAS"]]

    per_category = score(gold, pred)["per_category"]

    assert set(per_category) == {c.value for c in Category}
    assert per_category["NAME"]["recall"] == pytest.approx(0.5)
    assert per_category["DATE"]["recall"] == 1.0


def test_score_maps_unknown_type_to_other_category():
    # Fail-safe of category_for: an unexpected type is still counted, under OTHER.
    result = score([["B-UNSEEN_TYPE"]], [["B-UNSEEN_TYPE"]])

    assert result["per_category"]["OTHER"]["tp"] == 1
    assert result["per_type"]["UNSEEN_TYPE"]["tp"] == 1


def test_score_rejects_sentences_of_different_length():
    with pytest.raises(ValueError):
        score([["O", "B-PAIS"]], [["O"]])
    with pytest.raises(ValueError):
        score([["O"]], [["O"], ["O"]])


def test_score_matches_seqeval_on_mixed_sequences():
    seqeval_metrics = pytest.importorskip("seqeval.metrics")
    gold = [
        ["B-FECHAS", "I-FECHAS", "O", "B-PAIS", "B-CALLE", "I-CALLE"],
        ["O", "B-HOSPITAL", "I-HOSPITAL", "I-HOSPITAL", "O"],
    ]
    pred = [
        ["B-FECHAS", "I-FECHAS", "O", "I-PAIS", "B-CALLE", "O"],
        ["O", "B-HOSPITAL", "I-HOSPITAL", "I-HOSPITAL", "B-PAIS"],
    ]

    overall = score(gold, pred)["overall"]

    assert overall["precision"] == pytest.approx(seqeval_metrics.precision_score(gold, pred))
    assert overall["recall"] == pytest.approx(seqeval_metrics.recall_score(gold, pred))
    assert overall["f1"] == pytest.approx(seqeval_metrics.f1_score(gold, pred))


# --- first_subtoken_tags -----------------------------------------------------

ID2LABEL = {0: "O", 1: "B-PAIS", 2: "I-PAIS"}


def test_first_subtoken_tags_takes_the_first_sub_token_of_each_word():
    # <s> word0 word1a word1b </s>: word 1 is split into two sub-tokens.
    word_ids = [None, 0, 1, 1, None]
    pred_ids = [0, 1, 2, 0, 0]

    assert first_subtoken_tags(word_ids, pred_ids, ID2LABEL, n_words=2) == ["B-PAIS", "I-PAIS"]


def test_first_subtoken_tags_fills_truncated_words_with_o():
    # Words cut off by truncation get no prediction; "O" makes them count as missed (fail-safe).
    word_ids = [None, 0, None]
    pred_ids = [0, 1, 0]

    assert first_subtoken_tags(word_ids, pred_ids, ID2LABEL, n_words=3) == ["B-PAIS", "O", "O"]


# --- report ------------------------------------------------------------------


def _report() -> dict:
    gold = [["B-FECHAS", "O", "B-PAIS"]]
    pred = [["B-FECHAS", "O", "O"]]
    return {
        "configuration": "model_only",
        "model": {"run_id": 1, "base_model": "base/model", "base_model_revision": "abc"},
        "splits": {"dev": score(gold, pred), "test": score(gold, gold)},
    }


def test_markdown_report_has_overall_and_per_category_rows_for_each_split():
    markdown = render_markdown(_report())

    assert "## dev" in markdown
    assert "## test" in markdown
    assert "| NAME |" in markdown
    assert "| FECHAS |" in markdown
    assert "MEDDOCAN" in markdown  # attribution (CC BY 4.0)


def test_write_report_writes_json_and_markdown(tmp_path):
    report = _report()

    json_path, md_path = write_report(report, tmp_path)

    assert json.loads(json_path.read_text(encoding="utf-8")) == report
    assert md_path.read_text(encoding="utf-8") == render_markdown(report)
    assert json_path.name == "model_only.json"
    assert md_path.name == "model_only.md"
