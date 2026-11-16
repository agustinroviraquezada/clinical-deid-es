"""Model-only evaluation on MEDDOCAN dev and test (AC-02, requirements §7, task T2.4).

Decisions (T2.4):

- Metric: entity-level, strict span + type, micro-averaged. A predicted entity is a true
  positive only if its boundaries and its MEDDOCAN type both match a gold entity of the same
  sentence. Spans are measured on the BIO tokens produced by ``modeling.data_prep`` (same unit
  as the training metrics in ``run-<n>.json``), not on character offsets: the character-level
  path needs the product NER adapter (T2.6) and is used by the 3-configuration report (T3.4).
- Span decoding follows seqeval's default mode (an orphan ``I-`` starts an entity), so the
  numbers are comparable with the training log.
- Reported overall, per MEDDOCAN type and per product category (``MEDDOCAN_TO_CATEGORY``);
  category counts are the sum of their types' counts (still strict on the type).
- Only the first sub-token of each word is read; words lost to truncation are predicted ``O``,
  so they count as missed entities instead of disappearing from the metric.
- The report holds numbers only, never corpus text. It is written to
  ``src/clinical_deid/api/report/`` (ADR-0007) and cites MEDDOCAN (CC BY 4.0).
- The test split is evaluated once, with the final model; nothing is tuned on it.

Heavy imports (torch, transformers) happen inside ``predict_tags``, so the pure helpers can be
tested without the ``train`` dependency group.

Usage (from the repository root, with ``data/meddocan/bio`` built by ``modeling.data_prep``)::

    uv run --group train python -m modeling.evaluation.evaluate \\
        --model-dir "<runs-root>/run-1/model" --run-log modeling/training/runs/run-1.json
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from clinical_deid.domain.categories import MEDDOCAN_TO_CATEGORY, Category, category_for

CONFIGURATION = "model_only"
DEFAULT_OUT_DIR = Path("src/clinical_deid/api/report")
ATTRIBUTION = (
    "Data: MEDDOCAN corpus (Marimon et al., 2019), licensed CC BY 4.0. "
    "MEDDOCAN contains clinical case reports with synthetic personal data; "
    "performance on real notes will likely be lower."
)

Span = tuple[int, int, str]  # (start token, end token exclusive, MEDDOCAN type)


# --- Spans and metrics -------------------------------------------------------


def bio_to_spans(tags: Sequence[str]) -> set[Span]:
    """Decode BIO tags into typed token spans (end exclusive), seqeval default convention."""
    spans: set[Span] = set()
    start: int | None = None
    current: str | None = None
    for i, tag in enumerate(tags):
        prefix, _, type_ = tag.partition("-")
        continues = prefix == "I" and type_ == current
        if start is not None and not continues:
            spans.add((start, i, current))
            start, current = None, None
        if prefix in {"B", "I"} and not continues:
            start, current = i, type_
    if start is not None:
        spans.add((start, len(tags), current))
    return spans


def _metrics(tp: int, fp: int, fn: int) -> dict[str, float | int]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "support": tp + fn,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def score(gold_tags: Sequence[Sequence[str]], pred_tags: Sequence[Sequence[str]]) -> dict[str, Any]:
    """Strict span + type scores: ``overall``, ``per_type`` and ``per_category``."""
    if len(gold_tags) != len(pred_tags):
        raise ValueError(f"{len(gold_tags)} gold sentences but {len(pred_tags)} predicted")

    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    for i, (gold, pred) in enumerate(zip(gold_tags, pred_tags, strict=True)):
        if len(gold) != len(pred):
            raise ValueError(f"sentence {i}: {len(gold)} gold tags but {len(pred)} predicted")
        gold_spans, pred_spans = bio_to_spans(gold), bio_to_spans(pred)
        for *_, type_ in gold_spans & pred_spans:
            tp[type_] += 1
        for *_, type_ in pred_spans - gold_spans:
            fp[type_] += 1
        for *_, type_ in gold_spans - pred_spans:
            fn[type_] += 1

    types = sorted(set(MEDDOCAN_TO_CATEGORY) | set(tp) | set(fp) | set(fn))
    per_type = {t: _metrics(tp[t], fp[t], fn[t]) for t in types}

    per_category = {}
    for category in Category:
        members = [t for t in types if category_for(t) == category]
        per_category[category.value] = _metrics(
            sum(tp[t] for t in members), sum(fp[t] for t in members), sum(fn[t] for t in members)
        )

    overall = _metrics(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    return {"overall": overall, "per_type": per_type, "per_category": per_category}


# --- Inference (needs the ``train`` dependency group) ------------------------


def first_subtoken_tags(
    word_ids: Sequence[int | None],
    pred_ids: Sequence[int],
    id2label: Mapping[int, str],
    n_words: int,
) -> list[str]:
    """Word-level tags from sub-token predictions; words without a sub-token get ``O``."""
    tags = ["O"] * n_words
    previous: int | None = None
    for word_id, pred_id in zip(word_ids, pred_ids, strict=False):
        if word_id is not None and word_id != previous:
            tags[word_id] = id2label[int(pred_id)]
        previous = word_id
    return tags


def predict_tags(
    model_dir: Path, rows: Sequence[Mapping[str, Any]], batch_size: int = 32, max_length: int = 512
) -> list[list[str]]:
    """Run the fine-tuned model over pre-tokenized sentences and return word-level tags."""
    import torch
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_dir, add_prefix_space=True)
    model = AutoModelForTokenClassification.from_pretrained(model_dir)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    id2label = {int(k): v for k, v in model.config.id2label.items()}

    # Sorting by length keeps padding (and CPU time) low; the original order is restored below.
    order = sorted(range(len(rows)), key=lambda i: len(rows[i]["tokens"]))
    predictions: list[list[str]] = [[] for _ in rows]
    for start in range(0, len(order), batch_size):
        batch = order[start : start + batch_size]
        encoded = tokenizer(
            [rows[i]["tokens"] for i in batch],
            is_split_into_words=True,
            truncation=True,
            max_length=max_length,
            padding=True,
            return_tensors="pt",
        )
        with torch.no_grad():
            logits = model(
                input_ids=encoded["input_ids"].to(device),
                attention_mask=encoded["attention_mask"].to(device),
            ).logits
        pred_ids = logits.argmax(dim=-1).cpu().tolist()
        for j, i in enumerate(batch):
            predictions[i] = first_subtoken_tags(
                encoded.word_ids(j), pred_ids[j], id2label, len(rows[i]["tokens"])
            )
    return predictions


# --- Report ------------------------------------------------------------------


def _row(name: str, m: Mapping[str, Any]) -> str:
    return f"| {name} | {m['recall']:.3f} | {m['precision']:.3f} | {m['f1']:.3f} | {m['support']} |"


def _table(title: str, rows: Mapping[str, Mapping[str, Any]]) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| Name | Recall | Precision | F1 | Support |",
        "| --- | --- | --- | --- | --- |",
    ]
    lines += [_row(name, metrics) for name, metrics in rows.items()]
    return [*lines, ""]


def render_markdown(report: Mapping[str, Any]) -> str:
    model = report["model"]
    lines = [
        "# Model-only evaluation (MEDDOCAN)",
        "",
        "Entity-level, strict span + type, micro-averaged; spans on BIO tokens.",
        f"Model: run {model.get('run_id')} fine-tuned from `{model.get('base_model')}` "
        f"(revision `{model.get('base_model_revision')}`).",
        "AC-02 target on test: recall >= 0.90 and precision >= 0.85.",
        "",
    ]
    for split, result in report["splits"].items():
        lines += [f"## {split}", ""]
        lines += _table("Overall", {"overall": result["overall"]})
        lines += _table("Per category", result["per_category"])
        lines += _table("Per MEDDOCAN type", result["per_type"])
    lines += [ATTRIBUTION, ""]
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write ``model_only.json`` and ``model_only.md`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{CONFIGURATION}.json"
    md_path = out_dir / f"{CONFIGURATION}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


# --- CLI ---------------------------------------------------------------------


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _model_info(run_log: Path | None) -> dict[str, Any]:
    if run_log is None:
        return {"run_id": None, "base_model": None, "base_model_revision": None}
    log = json.loads(run_log.read_text(encoding="utf-8"))
    return {
        "run_id": log["run_id"],
        "base_model": log["config"]["model_name"],
        "base_model_revision": log["config"]["model_revision"],
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--run-log", type=Path, help="run-<n>.json of the evaluated model")
    parser.add_argument("--data-dir", type=Path, default=Path("data/meddocan/bio"))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--splits", nargs="+", default=["dev", "test"])
    parser.add_argument("--batch-size", type=int, default=32)
    args = parser.parse_args(argv)

    report: dict[str, Any] = {
        "configuration": CONFIGURATION,
        "metric": "entity-level strict span + type, micro-averaged, BIO token spans",
        "model": _model_info(args.run_log),
        "splits": {},
    }
    for split in args.splits:
        rows = _load_jsonl(args.data_dir / f"{split}.jsonl")
        pred = predict_tags(args.model_dir, rows, batch_size=args.batch_size)
        report["splits"][split] = score([row["tags"] for row in rows], pred)
        overall = report["splits"][split]["overall"]
        print(
            f"{split}: recall {overall['recall']:.4f} precision {overall['precision']:.4f} "
            f"f1 {overall['f1']:.4f} ({len(rows)} sentences)"
        )

    for path in write_report(report, args.out_dir):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
