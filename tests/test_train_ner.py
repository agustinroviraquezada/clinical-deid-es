"""Tests for the pure helpers of the fine-tuning module (T2.3).

They need neither torch nor transformers nor the network: the Trainer itself only runs on Colab.
"""

import json

import pytest

from clinical_deid.domain.categories import MEDDOCAN_TO_CATEGORY
from modeling.training.train_ner import (
    IGNORE_INDEX,
    MAX_RUNS,
    RunConfig,
    RunLimitError,
    align_labels,
    build_label_list,
    completed_runs,
    decode_predictions,
    next_run_id,
    prepare_run_dir,
    write_run_log,
)

# --- build_label_list ------------------------------------------------------


def test_label_list_covers_every_meddocan_type_with_o_first():
    labels = build_label_list()

    assert labels[0] == "O"
    assert len(labels) == 1 + 2 * len(MEDDOCAN_TO_CATEGORY)
    for type_ in MEDDOCAN_TO_CATEGORY:
        assert f"B-{type_}" in labels
        assert f"I-{type_}" in labels


def test_label_list_includes_types_missing_from_train():
    # ID_EMPLEO_PERSONAL_SANITARIO appears in dev but not in train (T2.1 stats).
    assert "B-ID_EMPLEO_PERSONAL_SANITARIO" in build_label_list()


def test_label_list_is_stable_between_calls():
    assert build_label_list() == build_label_list()


# --- align_labels ----------------------------------------------------------


LABEL2ID = {label: i for i, label in enumerate(build_label_list())}


def test_only_first_subtoken_of_each_word_gets_the_label():
    # <s> Ana(2 subtokens) Pérez </s>
    word_ids = [None, 0, 0, 1, None]
    tags = ["B-NOMBRE_SUJETO_ASISTENCIA", "I-NOMBRE_SUJETO_ASISTENCIA"]

    labels = align_labels(word_ids, tags, LABEL2ID)

    assert labels == [
        IGNORE_INDEX,
        LABEL2ID["B-NOMBRE_SUJETO_ASISTENCIA"],
        IGNORE_INDEX,
        LABEL2ID["I-NOMBRE_SUJETO_ASISTENCIA"],
        IGNORE_INDEX,
    ]


def test_truncated_sentence_keeps_labels_of_the_words_that_fit():
    word_ids = [None, 0, 1, None]  # word 2 was cut by max_length
    labels = align_labels(word_ids, ["O", "B-FECHAS", "I-FECHAS"], LABEL2ID)

    assert labels == [IGNORE_INDEX, LABEL2ID["O"], LABEL2ID["B-FECHAS"], IGNORE_INDEX]


def test_unknown_tag_fails_loudly_instead_of_training_on_a_wrong_label():
    with pytest.raises(ValueError, match="B-TIPO_INVENTADO"):
        align_labels([None, 0, None], ["B-TIPO_INVENTADO"], LABEL2ID)


# --- decode_predictions ----------------------------------------------------


def test_decode_predictions_skips_ignored_positions():
    id2label = {0: "O", 1: "B-FECHAS", 2: "I-FECHAS"}
    # Logits are already reduced with argmax: one row per sentence.
    predictions = [[0, 1, 2, 0], [0, 0, 1, 0]]
    label_ids = [[IGNORE_INDEX, 1, 2, IGNORE_INDEX], [IGNORE_INDEX, 0, 1, IGNORE_INDEX]]

    y_true, y_pred = decode_predictions(predictions, label_ids, id2label)

    assert y_true == [["B-FECHAS", "I-FECHAS"], ["O", "B-FECHAS"]]
    assert y_pred == [["B-FECHAS", "I-FECHAS"], ["O", "B-FECHAS"]]


# --- run bookkeeping (at most 3 runs) --------------------------------------


def test_first_run_gets_id_one(tmp_path):
    assert next_run_id(tmp_path) == 1


def test_run_id_counts_only_completed_runs(tmp_path):
    # An interrupted run has a checkpoint folder but no log: it is resumed, not counted.
    (tmp_path / "run-1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "run-2").mkdir()

    assert completed_runs(tmp_path) == 1
    assert next_run_id(tmp_path) == 2


def test_fourth_run_is_refused(tmp_path):
    for i in range(1, MAX_RUNS + 1):
        (tmp_path / f"run-{i}.json").write_text("{}", encoding="utf-8")

    with pytest.raises(RunLimitError):
        next_run_id(tmp_path)


def test_interrupted_run_is_reopened_with_the_same_config(tmp_path):
    config = RunConfig()
    first = prepare_run_dir(tmp_path, config)

    assert prepare_run_dir(tmp_path, config) == first == (1, tmp_path / "run-1")


def test_resuming_with_a_different_config_is_refused(tmp_path):
    prepare_run_dir(tmp_path, RunConfig(learning_rate=5e-5))

    with pytest.raises(ValueError, match="different config"):
        prepare_run_dir(tmp_path, RunConfig(learning_rate=3e-5))


@pytest.mark.security
def test_run_log_holds_hyperparameters_and_numeric_metrics_only(tmp_path):
    config = RunConfig(learning_rate=3e-5, num_train_epochs=2)
    metrics = {
        "eval_f1": 0.91,
        "eval_recall": 0.92,
        "eval_runtime": 12.5,
        "eval_text": "Paciente Ana Pérez",  # must never reach the log
    }

    path = write_run_log(tmp_path, 1, config, metrics)

    log = json.loads(path.read_text(encoding="utf-8"))
    assert path.name == "run-1.json"
    assert log["run_id"] == 1
    assert log["config"]["learning_rate"] == 3e-5
    assert log["config"]["model_revision"] == RunConfig().model_revision
    assert log["metrics"] == {"eval_f1": 0.91, "eval_recall": 0.92, "eval_runtime": 12.5}
    assert "Ana" not in path.read_text(encoding="utf-8")


def test_default_config_pins_the_base_model_revision():
    config = RunConfig()

    assert config.model_name == "BSC-LT/roberta-base-biomedical-clinical-es"
    assert len(config.model_revision) == 40  # full commit hash, not a branch name
