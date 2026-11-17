"""Tests for publishing the fine-tuned model on the Hugging Face Hub (T2.5).

They use a fake Hub client: no network, no token and no huggingface_hub dependency.
Model files are tiny placeholders; no weights or corpus text are used.
"""

import json
from pathlib import Path

import pytest

from modeling.publish.publish_model import (
    ALLOWED_FILES,
    build_model_card,
    publish,
    select_files,
    write_model_config,
)

RUN_LOG = {
    "config": {
        "model_name": "BSC-LT/roberta-base-biomedical-clinical-es",
        "model_revision": "af1b189bbc1303f23f64661a4a913c4da302d821",
        "num_train_epochs": 4,
        "learning_rate": 5e-05,
    },
}
REPORT = {
    "splits": {
        "test": {
            "overall": {"precision": 0.965, "recall": 0.974, "f1": 0.969, "support": 5661},
            "per_category": {
                "AGE": {"precision": 0.99, "recall": 0.98, "f1": 0.985, "support": 518},
                "NAME": {"precision": 0.97, "recall": 0.99, "f1": 0.98, "support": 900},
            },
        }
    }
}
REPO_ID = "someone/clinical-deid-es-meddocan"
SHA = "0123456789abcdef0123456789abcdef01234567"


def make_model_dir(tmp_path: Path, *extra: str) -> Path:
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    for name in ("config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json"):
        (model_dir / name).write_bytes(b"x")
    for name in extra:
        (model_dir / name).write_bytes(b"x")
    return model_dir


class FakeHub:
    def __init__(self, *, private: bool = True):
        self.private = private
        self.created: list[tuple[str, bool]] = []
        self.uploads: list[tuple[str, dict[str, Path | bytes]]] = []

    def whoami(self) -> str:
        return "someone"

    def create_private_repo(self, repo_id: str) -> None:
        self.created.append((repo_id, True))

    def is_private(self, repo_id: str) -> bool:
        return self.private

    def upload(self, repo_id: str, files: dict[str, Path | bytes], message: str) -> str:
        self.uploads.append((repo_id, files))
        return SHA


# --- Model card --------------------------------------------------------------


def test_model_card_cites_meddocan_and_its_licence():
    card = build_model_card(RUN_LOG, REPORT)

    assert "MEDDOCAN" in card
    assert "Marimon" in card
    assert "CC BY 4.0" in card
    assert "10.5281/zenodo.4279323" in card


def test_model_card_front_matter_declares_licence_language_and_base_model():
    card = build_model_card(RUN_LOG, REPORT)
    front_matter = card.split("---")[1]

    assert "license: apache-2.0" in front_matter
    assert "- es" in front_matter
    assert "base_model: BSC-LT/roberta-base-biomedical-clinical-es" in front_matter


def test_model_card_pins_base_model_revision_and_reports_test_metrics():
    card = build_model_card(RUN_LOG, REPORT)

    assert "af1b189bbc1303f23f64661a4a913c4da302d821" in card
    assert "0.974" in card  # overall test recall
    assert "| AGE |" in card


def test_model_card_warns_it_is_not_for_real_patient_data():
    assert "not a certified" in build_model_card(RUN_LOG, REPORT).lower()


# --- File selection ----------------------------------------------------------


@pytest.mark.security
def test_select_files_keeps_only_the_allowlist(tmp_path):
    model_dir = make_model_dir(tmp_path, "training_args.bin", "notes.txt")

    files = select_files(model_dir)

    assert set(files) == set(ALLOWED_FILES)
    assert "training_args.bin" not in files  # pickle: never published (supply chain)


def test_select_files_fails_without_safetensors_weights(tmp_path):
    model_dir = make_model_dir(tmp_path)
    (model_dir / "model.safetensors").unlink()
    (model_dir / "pytorch_model.bin").write_bytes(b"x")

    with pytest.raises(FileNotFoundError, match=r"model\.safetensors"):
        select_files(model_dir)


# --- Publishing --------------------------------------------------------------


def test_publish_creates_private_repo_uploads_card_and_returns_revision(tmp_path):
    hub = FakeHub()
    model_dir = make_model_dir(tmp_path, "training_args.bin")

    revision = publish(hub, REPO_ID, model_dir, card="# card")

    assert revision == SHA
    assert hub.created == [(REPO_ID, True)]
    ((repo_id, files),) = hub.uploads
    assert repo_id == REPO_ID
    assert files["README.md"] == b"# card"
    assert "training_args.bin" not in files


@pytest.mark.security
def test_publish_refuses_to_upload_to_a_public_repo(tmp_path):
    hub = FakeHub(private=False)

    with pytest.raises(RuntimeError, match="not private"):
        publish(hub, REPO_ID, make_model_dir(tmp_path), card="# card")

    assert hub.uploads == []


def test_publish_uploads_nothing_when_weights_are_missing(tmp_path):
    hub = FakeHub()
    model_dir = make_model_dir(tmp_path)
    (model_dir / "model.safetensors").unlink()

    with pytest.raises(FileNotFoundError):
        publish(hub, REPO_ID, model_dir, card="# card")

    assert hub.created == []
    assert hub.uploads == []


# --- Configuration -----------------------------------------------------------


def test_write_model_config_records_repo_and_revision(tmp_path):
    path = tmp_path / "config" / "model.json"

    write_model_config(path, REPO_ID, SHA)

    assert json.loads(path.read_text(encoding="utf-8")) == {"repo_id": REPO_ID, "revision": SHA}


@pytest.mark.parametrize("bad", ["main", "abc123", ""])
def test_write_model_config_rejects_anything_but_a_full_commit_sha(tmp_path, bad):
    with pytest.raises(ValueError, match="commit SHA"):
        write_model_config(tmp_path / "model.json", REPO_ID, bad)
