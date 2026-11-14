"""Token-classification fine-tuning on MEDDOCAN with ``transformers.Trainer`` (design §5, T2.3).

Runs on Colab from ``notebooks/train_colab.ipynb``. Decisions:

- Labels: BIO over the original MEDDOCAN types, taken from ``MEDDOCAN_TO_CATEGORY`` so every
  type gets a label even if it is missing from train (``ID_EMPLEO_PERSONAL_SANITARIO``).
- Only the first sub-token of each word carries a label; the rest are ignored by the loss.
- At most ``MAX_RUNS`` completed runs. A run is completed when ``run-<n>.json`` exists in the
  runs folder; an interrupted run is resumed from its last checkpoint instead of counting again.
- Checkpoints every epoch; the final model is saved as safetensors.
- The run log holds hyperparameters and numeric metrics only, never corpus text.

Heavy imports (torch, transformers, seqeval) happen inside the functions that need them, so the
pure helpers can be tested without the ``train`` dependency group.

Usage (from the repository root, with ``data/meddocan/bio`` built by ``modeling.data_prep``)::

    python -m modeling.training.train_ner --runs-root /content/drive/MyDrive/clinical-deid/runs
"""

from __future__ import annotations

import argparse
import json
import numbers
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from clinical_deid.domain.categories import MEDDOCAN_TO_CATEGORY

IGNORE_INDEX = -100  # label id ignored by the PyTorch cross-entropy loss
MAX_RUNS = 3

BASE_MODEL = "BSC-LT/roberta-base-biomedical-clinical-es"
# Pinned commit of the base model on the Hugging Face Hub (supply chain, design §8).
BASE_MODEL_REVISION = "af1b189bbc1303f23f64661a4a913c4da302d821"


class RunLimitError(RuntimeError):
    """The maximum number of training runs has already been completed."""


@dataclass(frozen=True)
class RunConfig:
    """Hyperparameters of one training run (logged as-is)."""

    model_name: str = BASE_MODEL
    model_revision: str = BASE_MODEL_REVISION
    learning_rate: float = 5e-5
    num_train_epochs: int = 4
    per_device_train_batch_size: int = 16
    per_device_eval_batch_size: int = 32
    max_length: int = 512
    weight_decay: float = 0.01
    warmup_steps: float = 0.1  # a float in [0, 1) is a ratio of total steps (transformers 5)
    seed: int = 42


# --- Labels ------------------------------------------------------------------


def build_label_list() -> list[str]:
    """``O`` followed by ``B-``/``I-`` for every MEDDOCAN type, in a stable order."""
    labels = ["O"]
    for type_ in sorted(MEDDOCAN_TO_CATEGORY):
        labels += [f"B-{type_}", f"I-{type_}"]
    return labels


def align_labels(
    word_ids: Sequence[int | None], tags: Sequence[str], label2id: Mapping[str, int]
) -> list[int]:
    """Map word-level BIO tags onto sub-tokens.

    Special tokens (``None``) and every sub-token after the first one of a word get
    ``IGNORE_INDEX``. Words cut off by truncation simply do not appear in ``word_ids``.
    An unknown tag raises ``ValueError``: training on a silently wrong label is worse than
    stopping.
    """
    unknown = sorted(set(tags) - set(label2id))
    if unknown:
        raise ValueError(f"tags not in the label list: {', '.join(unknown)}")

    labels = []
    previous: int | None = None
    for word_id in word_ids:
        if word_id is None or word_id == previous:
            labels.append(IGNORE_INDEX)
        else:
            labels.append(label2id[tags[word_id]])
        previous = word_id
    return labels


def decode_predictions(
    predictions: Sequence[Sequence[int]],
    label_ids: Sequence[Sequence[int]],
    id2label: Mapping[int, str],
) -> tuple[list[list[str]], list[list[str]]]:
    """Turn arg-maxed predictions and gold ids into tag sequences, skipping ignored positions."""
    y_true, y_pred = [], []
    for pred_row, gold_row in zip(predictions, label_ids, strict=True):
        pairs = [
            (id2label[int(g)], id2label[int(p)])
            for p, g in zip(pred_row, gold_row, strict=True)
            if g != IGNORE_INDEX
        ]
        y_true.append([g for g, _ in pairs])
        y_pred.append([p for _, p in pairs])
    return y_true, y_pred


# --- Run bookkeeping ---------------------------------------------------------


def completed_runs(runs_root: Path) -> int:
    return len(list(runs_root.glob("run-*.json")))


def next_run_id(runs_root: Path) -> int:
    """Id of the run to start or resume; raise ``RunLimitError`` after ``MAX_RUNS``."""
    done = completed_runs(runs_root)
    if done >= MAX_RUNS:
        raise RunLimitError(f"{done} runs already completed (maximum {MAX_RUNS}, design §5)")
    return done + 1


def prepare_run_dir(runs_root: Path, config: RunConfig) -> tuple[int, Path]:
    """Create (or reopen) the folder of the next run.

    The config is stored on the first attempt; resuming with different hyperparameters raises
    ``ValueError``, so one run never mixes two configurations.
    """
    run_id = next_run_id(runs_root)
    run_dir = runs_root / f"run-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    config_path = run_dir / "run_config.json"
    if config_path.exists():
        stored = json.loads(config_path.read_text(encoding="utf-8"))
        if stored != asdict(config):
            raise ValueError(
                f"{run_dir.name} was started with a different config; "
                "resume it with the same RunConfig or delete the folder"
            )
    else:
        config_path.write_text(json.dumps(asdict(config), indent=2), encoding="utf-8")
    return run_id, run_dir


def write_run_log(
    runs_root: Path, run_id: int, config: RunConfig, metrics: Mapping[str, Any]
) -> Path:
    """Write ``run-<n>.json`` with the hyperparameters and the numeric metrics only."""
    numeric = {
        key: float(value)
        for key, value in metrics.items()
        if isinstance(value, numbers.Real) and not isinstance(value, bool)
    }
    log = {"run_id": run_id, "config": asdict(config), "metrics": numeric}
    path = runs_root / f"run-{run_id}.json"
    path.write_text(json.dumps(log, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# --- Training (needs the ``train`` dependency group) -------------------------


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _encode(rows, tokenizer, label2id, max_length) -> tuple[list[dict[str, Any]], int]:
    """Tokenize sentences and align labels; also count truncated sentences."""
    encoded = tokenizer(
        [row["tokens"] for row in rows],
        is_split_into_words=True,
        truncation=True,
        max_length=max_length,
    )
    features, truncated = [], 0
    for i, row in enumerate(rows):
        word_ids = encoded.word_ids(i)
        seen = {w for w in word_ids if w is not None}
        truncated += len(seen) < len(row["tokens"])
        features.append(
            {
                "input_ids": encoded["input_ids"][i],
                "attention_mask": encoded["attention_mask"][i],
                "labels": align_labels(word_ids, row["tags"], label2id),
            }
        )
    return features, truncated


def _metrics_function(id2label: Mapping[int, str]):
    import numpy as np
    from seqeval.metrics import classification_report, f1_score, precision_score, recall_score

    def compute_metrics(eval_pred) -> dict[str, float]:
        logits, label_ids = eval_pred
        y_true, y_pred = decode_predictions(np.argmax(logits, axis=-1), label_ids, id2label)
        metrics = {
            "precision": precision_score(y_true, y_pred),
            "recall": recall_score(y_true, y_pred),
            "f1": f1_score(y_true, y_pred),
        }
        report = classification_report(y_true, y_pred, output_dict=True, zero_division=0)
        for type_ in MEDDOCAN_TO_CATEGORY:
            if type_ in report:
                metrics[f"recall_{type_}"] = report[type_]["recall"]
                metrics[f"f1_{type_}"] = report[type_]["f1-score"]
        return metrics

    return compute_metrics


def train(config: RunConfig, data_dir: Path, runs_root: Path) -> Path:
    """Fine-tune, evaluate on dev and save the model as safetensors. Returns the run log path.

    ``runs_root`` should be on persistent storage (Google Drive) so checkpoints survive a
    disconnected Colab session; calling ``train`` again resumes the interrupted run.
    """
    import torch
    from transformers import (
        AutoModelForTokenClassification,
        AutoTokenizer,
        DataCollatorForTokenClassification,
        Trainer,
        TrainingArguments,
        set_seed,
    )
    from transformers.trainer_utils import get_last_checkpoint

    runs_root.mkdir(parents=True, exist_ok=True)
    run_id, run_dir = prepare_run_dir(runs_root, config)
    set_seed(config.seed)

    labels = build_label_list()
    label2id = {label: i for i, label in enumerate(labels)}
    id2label = dict(enumerate(labels))

    tokenizer = AutoTokenizer.from_pretrained(
        config.model_name, revision=config.model_revision, add_prefix_space=True
    )
    model = AutoModelForTokenClassification.from_pretrained(
        config.model_name,
        revision=config.model_revision,
        num_labels=len(labels),
        id2label=id2label,
        label2id=label2id,
    )

    train_set, train_truncated = _encode(
        _load_jsonl(data_dir / "train.jsonl"), tokenizer, label2id, config.max_length
    )
    dev_set, dev_truncated = _encode(
        _load_jsonl(data_dir / "dev.jsonl"), tokenizer, label2id, config.max_length
    )

    args = TrainingArguments(
        output_dir=str(run_dir),
        learning_rate=config.learning_rate,
        num_train_epochs=config.num_train_epochs,
        per_device_train_batch_size=config.per_device_train_batch_size,
        per_device_eval_batch_size=config.per_device_eval_batch_size,
        weight_decay=config.weight_decay,
        warmup_steps=config.warmup_steps,
        seed=config.seed,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        fp16=torch.cuda.is_available(),
        logging_steps=50,
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=train_set,
        eval_dataset=dev_set,
        data_collator=DataCollatorForTokenClassification(tokenizer),
        processing_class=tokenizer,
        compute_metrics=_metrics_function(id2label),
    )

    train_result = trainer.train(resume_from_checkpoint=get_last_checkpoint(str(run_dir)))
    dev_metrics = trainer.evaluate()  # best checkpoint, thanks to load_best_model_at_end

    model_dir = run_dir / "model"
    trainer.save_model(str(model_dir))  # safetensors is the transformers default
    if not (model_dir / "model.safetensors").exists():
        raise RuntimeError(f"{model_dir} has no model.safetensors (design §5)")

    metrics = {
        **train_result.metrics,
        **dev_metrics,
        "train_truncated_sentences": train_truncated,
        "dev_truncated_sentences": dev_truncated,
    }
    return write_run_log(runs_root, run_id, config, metrics)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path("data/meddocan/bio"))
    parser.add_argument("--runs-root", type=Path, required=True)
    defaults = RunConfig()
    for field in fields(RunConfig):
        parser.add_argument(
            f"--{field.name.replace('_', '-')}",
            type=type(getattr(defaults, field.name)),
            default=getattr(defaults, field.name),
        )
    args = vars(parser.parse_args(argv))
    data_dir, runs_root = args.pop("data_dir"), args.pop("runs_root")
    log_path = train(RunConfig(**args), data_dir, runs_root)
    print(log_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
