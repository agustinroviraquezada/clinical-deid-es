"""Cascade threshold and N chosen on MEDDOCAN dev (FR-05, FR-07, design §3, task T3.1).

Decisions (T3.1):

- Confidence is the score of the product NER adapter (``HFEntityDetector``): with
  ``aggregation_strategy="first"`` it is the mean, over the entity's words, of the probability of
  the predicted label on each word's first sub-token ("mean token probability", ADR-0004).
- Entities are matched to the gold BRAT annotations on character offsets, strict span + type,
  using the same overlap resolution as the training data (``resolve_overlaps``).
- For each candidate threshold ``t`` the *uncertain bucket* is the set of entities with
  confidence < t (the ones the cascade would send to the LLM). The *band* of ``t`` is the set
  of entities between the previous candidate and ``t``; its precision is the share of those
  entities that are correct.
- Threshold rule (ADR-0009): ``t`` = upper edge of the highest non-empty band with precision
  < 0.85, so every band at or above ``t`` is reliable and every unreliable band goes to the LLM.
  The first design's rule (maximise recall with precision >= 0.85) is always met by this model,
  so it would give t = 0; the cumulative bucket precision never reaches 0.85 because the
  low-confidence entities drag it down, so it would always pick the top candidate. If no band
  is unreliable, the lowest candidate is used (almost no LLM calls).
- N = 95th percentile (nearest rank) of uncertain entities per document at the chosen
  threshold, at least 1. Documents above N mask the rest by default (FR-07).
- The report holds numbers only, never corpus text. Test is not used: it is reserved for the
  final report.

Usage (from the repository root, with MEDDOCAN in ``data/meddocan``)::

    uv run --group train python -m modeling.evaluation.threshold --model-dir "<run>/model"
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from clinical_deid.domain.entities import Entity
from clinical_deid.ports import EntityDetector
from modeling.data_prep.brat_to_bio import parse_ann, resolve_overlaps

DEFAULT_OUT_DIR = Path("src/clinical_deid/api/report")
REPORT_NAME = "threshold_dev"
MAX_BUCKET_PRECISION = 0.85
N_PERCENTILE = 95
THRESHOLDS = [round(0.30 + 0.05 * i, 2) for i in range(13)] + [
    0.91,
    0.92,
    0.93,
    0.94,
    0.95,
    0.96,
    0.97,
    0.98,
    0.99,
    1.0,
]
RULE = (
    "threshold = upper edge of the highest confidence band with precision < "
    f"{MAX_BUCKET_PRECISION}; N = p{N_PERCENTILE} of uncertain entities per document (min 1)"
)
ATTRIBUTION = (
    "Data: MEDDOCAN corpus (Marimon et al., 2019), licensed CC BY 4.0. "
    "MEDDOCAN contains clinical case reports with synthetic personal data; "
    "performance on real notes will likely be lower."
)

GoldSpan = tuple[int, int, str]  # (start char, end char exclusive, MEDDOCAN type)


@dataclass(frozen=True, slots=True)
class ScoredEntity:
    """A predicted entity reduced to numbers: its confidence and whether it matches gold."""

    confidence: float
    correct: bool


@dataclass(frozen=True, slots=True)
class DocScore:
    """Predicted entities of one document and its number of gold entities."""

    doc_id: str
    entities: list[ScoredEntity]
    n_gold: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# --- Matching ----------------------------------------------------------------


def match_entities(predicted: Iterable[Entity], gold: set[GoldSpan]) -> list[ScoredEntity]:
    """Mark each predicted entity as correct if its span and type match a gold one."""
    return [
        ScoredEntity(confidence=e.confidence, correct=(e.start, e.end, e.type) in gold)
        for e in predicted
    ]


def score_documents(
    detector: EntityDetector, documents: Iterable[tuple[str, str, set[GoldSpan]]]
) -> list[DocScore]:
    """Run ``detector`` on each ``(doc_id, text, gold)`` and keep numbers only."""
    return [
        DocScore(doc_id, match_entities(detector.detect(text), gold), len(gold))
        for doc_id, text, gold in documents
    ]


# --- Curve and choices -------------------------------------------------------


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def threshold_curve(docs: Sequence[DocScore], thresholds: Sequence[float]) -> list[dict[str, Any]]:
    """Precision and recall of the accepted and uncertain entities at each threshold."""
    entities = [e for doc in docs for e in doc.entities]
    n_gold = sum(doc.n_gold for doc in docs)
    n_correct = sum(e.correct for e in entities)
    curve = []
    previous = 0.0
    for t in thresholds:
        uncertain = [e for e in entities if e.confidence < t]
        uncertain_correct = sum(e.correct for e in uncertain)
        band = [e for e in uncertain if e.confidence >= previous]
        previous = t
        accepted_correct = n_correct - uncertain_correct
        curve.append(
            {
                "threshold": t,
                "n_uncertain": len(uncertain),
                "uncertain_share": _ratio(len(uncertain), len(entities)),
                "uncertain_precision": _ratio(uncertain_correct, len(uncertain)),
                "band_n": len(band),
                "band_precision": _ratio(sum(e.correct for e in band), len(band)),
                "accepted_precision": _ratio(accepted_correct, len(entities) - len(uncertain)),
                "accepted_recall": _ratio(accepted_correct, n_gold),
                "model_precision": _ratio(n_correct, len(entities)),
                "model_recall": _ratio(n_correct, n_gold),
                "uncertain_per_doc": [sum(e.confidence < t for e in doc.entities) for doc in docs],
            }
        )
    return curve


def choose_threshold(
    curve: Sequence[Mapping[str, Any]], max_bucket_precision: float = MAX_BUCKET_PRECISION
) -> float:
    """Upper edge of the highest non-empty band whose precision is below the limit."""
    qualifying = [
        row["threshold"]
        for row in curve
        if row["band_n"] and row["band_precision"] < max_bucket_precision
    ]
    return max(qualifying) if qualifying else min(row["threshold"] for row in curve)


def percentile(values: Sequence[int], q: float) -> int:
    """Nearest-rank percentile; 0 for an empty list."""
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


def choose_n(uncertain_per_doc: Sequence[int], q: float = N_PERCENTILE) -> int:
    """N = the given percentile of uncertain entities per document, at least 1."""
    return max(1, percentile(uncertain_per_doc, q))


# --- Report ------------------------------------------------------------------


def _fmt(value: float | None) -> str:
    return "—" if value is None else f"{value:.3f}"


def render_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        f"# Cascade threshold and N on MEDDOCAN {report['split']}",
        "",
        f"Rule: {report['rule']}.",
        "Entities matched to gold on character offsets, strict span + type.",
        "",
        f"**Chosen threshold: {report['threshold']:.2f} · N = {report['n']}**",
        "",
        "| Threshold | Band n | Band P | Uncertain | Share | Uncertain P | Accepted P "
        "| Accepted R | p50/doc | p90/doc | p95/doc | max/doc |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["curve"]:
        per_doc = row["uncertain_per_doc"]
        lines.append(
            f"| {row['threshold']:.2f} | {row['band_n']} | {_fmt(row['band_precision'])} "
            f"| {row['n_uncertain']} | {_fmt(row['uncertain_share'])} "
            f"| {_fmt(row['uncertain_precision'])} | {_fmt(row['accepted_precision'])} "
            f"| {_fmt(row['accepted_recall'])} | {percentile(per_doc, 50)} "
            f"| {percentile(per_doc, 90)} | {percentile(per_doc, 95)} "
            f"| {max(per_doc, default=0)} |"
        )
    first = report["curve"][0]
    lines += [
        "",
        f"Model only: precision {_fmt(first['model_precision'])}, "
        f"recall {_fmt(first['model_recall'])}.",
        "",
        ATTRIBUTION,
        "",
    ]
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write ``threshold_dev.json`` and ``threshold_dev.md`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{REPORT_NAME}.json"
    md_path = out_dir / f"{REPORT_NAME}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


# --- CLI ---------------------------------------------------------------------


def _read(path: Path) -> str:
    # newline="" keeps "\r\n" intact so BRAT character offsets stay valid.
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def load_brat(brat_dir: Path) -> list[tuple[str, str, set[GoldSpan]]]:
    """``(doc_id, text, gold spans)`` for every document of a BRAT folder."""
    documents = []
    for txt_path in sorted(brat_dir.glob("*.txt")):
        spans, _ = resolve_overlaps(parse_ann(_read(txt_path.with_suffix(".ann"))))
        gold = {(s.start, s.end, s.type) for s in spans}
        documents.append((txt_path.stem, _read(txt_path), gold))
    return documents


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=Path("data/meddocan"))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args(argv)

    from clinical_deid.adapters.hf_ner import HFEntityDetector

    detector = HFEntityDetector.from_pretrained(args.model_dir)
    docs = score_documents(detector, load_brat(args.corpus / "dev" / "brat"))
    curve = threshold_curve(docs, THRESHOLDS)
    threshold = choose_threshold(curve)
    chosen = next(row for row in curve if row["threshold"] == threshold)
    report = {
        "split": "dev",
        "n_documents": len(docs),
        "rule": RULE,
        "threshold": threshold,
        "n": choose_n(chosen["uncertain_per_doc"]),
        "curve": curve,
    }
    print(f"threshold {threshold:.2f}, N {report['n']} ({len(docs)} documents)")
    for path in write_report(report, args.out_dir):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
