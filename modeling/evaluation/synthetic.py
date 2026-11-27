"""Precomputed results on the synthetic demo notes (FR-12, task T4.4).

The synthetic notes in ``api/static/examples.json`` imitate styles MEDDOCAN does not cover
(terse progress notes, abbreviations, discharge reports...). They were written with an LLM and
reviewed by hand; their personal data are invented. The hand-made gold annotations live in
``synthetic_gold.json`` next to this module as ``[surface text, MEDDOCAN type]`` pairs: every
whole-word occurrence of the surface in the note is one entity.

The report keeps, per note, the model-only masked output, its entities, what it missed and how
many entities the cascade would send to the LLM (confidence below the threshold). ``cascade``
and ``llm_only`` stay ``pending`` until Bedrock is available, as in ``comparison.json``.
Unlike the MEDDOCAN comparison, this report does hold text, because the notes are synthetic
and already public in ``examples.json``.

Usage (from the repository root)::

    uv run --group train python -m modeling.evaluation.synthetic --model-dir "<run>/model"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from clinical_deid.domain.categories import category_for
from clinical_deid.domain.entities import Entity
from clinical_deid.domain.masker import mask
from modeling.evaluation.compare import score_spans
from modeling.evaluation.evaluate import _metrics
from modeling.evaluation.threshold import GoldSpan

DEFAULT_EXAMPLES = Path("src/clinical_deid/api/static/examples.json")
DEFAULT_GOLD = Path(__file__).with_name("synthetic_gold.json")
DEFAULT_OUT_DIR = Path("src/clinical_deid/api/report")
REPORT_NAME = "synthetic_examples"
ABOUT = (
    "Synthetic demo notes written with an LLM and reviewed by hand; all personal data are "
    "invented. Scores use strict character span + category on a handful of notes: they "
    "illustrate behaviour on other styles, they are not a benchmark."
)

Note = tuple[Mapping[str, Any], str, set[GoldSpan]]  # (example, style, gold spans)
Predict = Callable[[str], list[Entity]]


def text_digest(text: str) -> str:
    """SHA-256 of a note, so a stale report can be detected without re-running the model."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def gold_spans(text: str, entities: Iterable[Sequence[str]]) -> set[GoldSpan]:
    """Turn ``[surface, type]`` pairs into character spans (every whole-word occurrence).

    Raises ``ValueError`` if a surface is not in the text or two spans overlap, so a typo in
    the hand-made annotations cannot go unnoticed.
    """
    spans: set[GoldSpan] = set()
    for surface, type_ in entities:
        pattern = re.compile(rf"(?<!\w){re.escape(surface)}(?!\w)")
        found = [(m.start(), m.end(), type_) for m in pattern.finditer(text)]
        if not found:
            raise ValueError(f"Gold surface not found in the note: {surface!r}")
        spans.update(found)

    ordered = sorted(spans)
    for (_, end, _), (start, _, _) in zip(ordered, ordered[1:], strict=False):
        if start < end:
            raise ValueError(f"Gold spans overlap at offset {start}")
    return spans


def load_synthetic(examples: Iterable[Mapping[str, Any]], gold: Mapping[str, Any]) -> list[Note]:
    """Synthetic examples paired with their style and gold spans."""
    return [
        (
            example,
            gold[example["id"]]["style"],
            gold_spans(example["text"], gold[example["id"]]["entities"]),
        )
        for example in examples
        if example["source"] == "synthetic"
    ]


def _model_only(text: str, gold: set[GoldSpan], predict: Predict, threshold: float) -> dict:
    entities = predict(text)
    scores = score_spans([gold], [entities])["overall"]
    predicted = {(e.start, e.end, e.category.value) for e in entities}
    gold_with_category = sorted((s, e, category_for(t).value) for s, e, t in gold)
    return {
        "status": "done",
        "masked": mask(text, entities),
        "entities": [
            {
                "start": e.start,
                "end": e.end,
                "category": e.category.value,
                "confidence": round(e.confidence, 4),
            }
            for e in entities
        ],
        "missed": [
            {"start": s, "end": e, "category": c}
            for s, e, c in gold_with_category
            if (s, e, c) not in predicted
        ],
        "n_uncertain": sum(e.confidence < threshold for e in entities),
        "tp": scores["tp"],
        "fp": scores["fp"],
        "fn": scores["fn"],
    }


def build_report(notes: Sequence[Note], predict: Predict, threshold: float) -> dict[str, Any]:
    """Model-only results per note; ``cascade`` and ``llm_only`` stay pending."""
    rows = []
    for example, style, gold in notes:
        rows.append(
            {
                "id": example["id"],
                "title": example["title"],
                "style": style,
                "text_sha256": text_digest(example["text"]),
                "n_gold": len(gold),
                "configurations": {
                    "model_only": _model_only(example["text"], gold, predict, threshold),
                    "cascade": {"status": "pending"},
                    "llm_only": {"status": "pending"},
                },
            }
        )
    tp = sum(r["configurations"]["model_only"]["tp"] for r in rows)
    fp = sum(r["configurations"]["model_only"]["fp"] for r in rows)
    fn = sum(r["configurations"]["model_only"]["fn"] for r in rows)
    return {
        "about": ABOUT,
        "threshold": threshold,
        "overall": {"model_only": _metrics(tp, fp, fn)},
        "examples": rows,
    }


def render_markdown(report: Mapping[str, Any]) -> str:
    """Short human-readable summary (numbers only)."""
    lines = [
        "# Synthetic demo notes: precomputed results",
        "",
        report["about"],
        "",
        f"Cascade threshold: {report['threshold']}. Cascade and LLM only: pending (Bedrock).",
        "",
        "| Note | Style | Gold | TP | FP | FN | Uncertain |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["examples"]:
        m = row["configurations"]["model_only"]
        lines.append(
            f"| {row['id']} | {row['style']} | {row['n_gold']} | {m['tp']} | {m['fp']} "
            f"| {m['fn']} | {m['n_uncertain']} |"
        )
    o = report["overall"]["model_only"]
    lines += [
        "",
        f"Model only, all notes: precision {o['precision']:.3f}, recall {o['recall']:.3f}, "
        f"F1 {o['f1']:.3f}.",
        "",
    ]
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{REPORT_NAME}.json"
    md_path = out_dir / f"{REPORT_NAME}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--examples", type=Path, default=DEFAULT_EXAMPLES)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    from clinical_deid.adapters.hf_ner import HFEntityDetector
    from clinical_deid.config import get_settings

    examples = json.loads(args.examples.read_text(encoding="utf-8"))
    gold = json.loads(args.gold.read_text(encoding="utf-8"))
    detector = HFEntityDetector.from_pretrained(args.model_dir)
    report = build_report(
        load_synthetic(examples, gold), detector.detect, get_settings().confidence_threshold
    )
    for path in write_report(report, args.out_dir):
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
