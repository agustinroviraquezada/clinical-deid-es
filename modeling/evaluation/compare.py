"""Comparison of the 3 configurations on MEDDOCAN test (AC-05, requirements §7, task T3.4).

Configurations: ``model_only`` (the NER model masks everything it finds), ``llm_only`` (the LLM
reads the whole document, ADR-0011) and ``cascade`` (the product: the model, plus the LLM for
uncertain entities, with the threshold and N chosen on dev in T3.1).

Decisions (T3.4):

- Metric: entity-level, strict character span + **product category**, micro-averaged, overall and
  per category. Category, not MEDDOCAN type, because the cascade's LLM relabels entities with a
  category and the LLM-only baseline only knows categories; the user sees categories too.
  Gold spans come from the BRAT files with the same overlap resolution as training.
- Model only and cascade run on all test documents; LLM only on a fixed random sample of 50
  (seeded, requirements §7).
- A document whose prediction fails (e.g. an LLM-only reply outside the schema) counts as
  predicting nothing: its entities are missed. The cascade never fails here: it masks instead.
- Cost: real token counts read from each Bedrock reply (``UsageCountingClient``) times the list
  price below; model-only has no per-call cost (Lambda compute is outside this comparison).
- Latency: wall-clock per document on the machine that runs the evaluation (not Lambda).
- Configurations can be run separately: results not re-run are kept from the previous report,
  and configurations never run are marked ``pending``.
- The report holds numbers only, never corpus text, and cites MEDDOCAN (CC BY 4.0).

Usage (from the repository root, with MEDDOCAN in ``data/meddocan``)::

    uv run --group train python -m modeling.evaluation.compare \\
        --model-dir "<run>/model" --configs model_only cascade llm_only
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from clinical_deid.adapters.bedrock_llm import BedrockRuntimeClient
from clinical_deid.domain.categories import Category, category_for
from clinical_deid.domain.entities import Entity
from modeling.evaluation.evaluate import _metrics
from modeling.evaluation.threshold import GoldSpan, load_brat

CONFIGURATIONS = ("model_only", "llm_only", "cascade")
DEFAULT_OUT_DIR = Path("src/clinical_deid/api/report")
REPORT_NAME = "comparison"
LLM_ONLY_SAMPLE = 50
SEED = 2026
# USD per million tokens, Claude Haiku 4.5 with the EU inference profile (docs/feasibility.md);
# to be checked against the AWS bill after the run.
PRICES = {"input": 1.10, "output": 5.50}
LLM_ONLY_READ_TIMEOUT_S = 60
ATTRIBUTION = (
    "Data: MEDDOCAN corpus (Marimon et al., 2019), licensed CC BY 4.0. "
    "MEDDOCAN contains clinical case reports with synthetic personal data; "
    "performance on real notes will likely be lower."
)

Document = tuple[str, str, set[GoldSpan]]  # (doc id, text, gold spans)
Predict = Callable[[str], list[Entity]]


# --- Scores ------------------------------------------------------------------


def score_spans(
    gold_docs: Sequence[set[GoldSpan]], pred_docs: Sequence[Iterable[Entity]]
) -> dict[str, Any]:
    """Strict character span + category scores: ``overall`` and ``per_category``."""
    if len(gold_docs) != len(pred_docs):
        raise ValueError(f"{len(gold_docs)} gold documents but {len(pred_docs)} predicted")

    tp: Counter[str] = Counter()
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    for gold, pred in zip(gold_docs, pred_docs, strict=True):
        gold_set = {(s, e, category_for(t).value) for s, e, t in gold}
        pred_set = {(e.start, e.end, e.category.value) for e in pred}
        for *_, category in gold_set & pred_set:
            tp[category] += 1
        for *_, category in pred_set - gold_set:
            fp[category] += 1
        for *_, category in gold_set - pred_set:
            fn[category] += 1

    per_category = {c.value: _metrics(tp[c.value], fp[c.value], fn[c.value]) for c in Category}
    overall = _metrics(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    return {"overall": overall, "per_category": per_category}


# --- Cost, latency and sample ------------------------------------------------


class UsageCountingClient:
    """Wraps a ``bedrock-runtime`` client and adds up the tokens Bedrock reports per call."""

    def __init__(self, client: BedrockRuntimeClient) -> None:
        self._client = client
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.calls += 1  # Failed calls are counted too: they may still be billed.
        response = self._client.converse(**kwargs)
        usage = response.get("usage") if isinstance(response, dict) else None
        if isinstance(usage, dict):
            self.input_tokens += _int(usage.get("inputTokens"))
            self.output_tokens += _int(usage.get("outputTokens"))
        return response


def _int(value: Any) -> int:
    return value if isinstance(value, int) and value > 0 else 0


def cost_summary(
    usage: UsageCountingClient | None, n_documents: int, prices: Mapping[str, float] = PRICES
) -> dict[str, Any]:
    """LLM calls, tokens and USD (total and per document) of one configuration run."""
    if usage is None:
        calls, input_tokens, output_tokens = 0, 0, 0
    else:
        calls, input_tokens, output_tokens = usage.calls, usage.input_tokens, usage.output_tokens
    usd = (input_tokens * prices["input"] + output_tokens * prices["output"]) / 1_000_000
    return {
        "llm_calls": calls,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "usd_total": usd,
        "usd_per_document": usd / n_documents if n_documents else 0.0,
    }


def _nearest_rank(ordered: Sequence[float], q: float) -> float:
    return ordered[max(1, math.ceil(q / 100 * len(ordered))) - 1]


def latency_stats(seconds: Sequence[float]) -> dict[str, float]:
    """Mean, p50, p95 (nearest rank) and max of per-document latencies, in seconds."""
    if not seconds:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    ordered = sorted(seconds)
    return {
        "mean": sum(ordered) / len(ordered),
        "p50": _nearest_rank(ordered, 50),
        "p95": _nearest_rank(ordered, 95),
        "max": ordered[-1],
    }


def sample_documents(documents: Sequence[Document], k: int, seed: int = SEED) -> list[Document]:
    """A seeded sample of ``k`` documents (all if fewer), independent of input order."""
    ordered = sorted(documents, key=lambda d: d[0])
    chosen = ordered if k >= len(ordered) else random.Random(seed).sample(ordered, k)  # noqa: S311 — sampling, not crypto.
    return sorted(chosen, key=lambda d: d[0])


# --- Run ---------------------------------------------------------------------


def run_configuration(
    documents: Sequence[Document],
    predict: Predict,
    usage: UsageCountingClient | None = None,
    clock: Callable[[], float] = time.perf_counter,
    prices: Mapping[str, float] = PRICES,
) -> dict[str, Any]:
    """Run ``predict`` on each document and keep numbers only: scores, latency and cost."""
    predictions: list[list[Entity]] = []
    latencies: list[float] = []
    failures = 0
    for _, text, _ in documents:
        started = clock()
        try:
            entities = predict(text)
        except Exception:  # noqa: BLE001 — a failed document predicts nothing (missed entities).
            entities = []
            failures += 1
        latencies.append(clock() - started)
        predictions.append(entities)

    scores = score_spans([gold for *_, gold in documents], predictions)
    return {
        "status": "done",
        "n_documents": len(documents),
        "n_failures": failures,
        **scores,
        "latency_s": latency_stats(latencies),
        "cost": cost_summary(usage, len(documents), prices),
    }


# --- Report ------------------------------------------------------------------


def merge_report(
    previous: Mapping[str, Any] | None,
    results: Mapping[str, Mapping[str, Any]],
    meta: Mapping[str, Any],
) -> dict[str, Any]:
    """New results over the previous report's; configurations never run are ``pending``."""
    old = (previous or {}).get("configurations", {})
    configurations = {
        name: dict(results.get(name) or old.get(name) or {"status": "pending"})
        for name in CONFIGURATIONS
    }
    return {**(previous or {}), **meta, "configurations": configurations}


def _overall_row(name: str, result: Mapping[str, Any]) -> str:
    if result.get("status") != "done":
        return f"| {name} | pending | | | | | | |"
    m, lat, cost = result["overall"], result["latency_s"], result["cost"]
    return (
        f"| {name} | {result['n_documents']} | {m['recall']:.3f} | {m['precision']:.3f} | "
        f"{m['f1']:.3f} | {lat['p50']:.2f} / {lat['p95']:.2f} | {cost['usd_per_document']:.5f} | "
        f"{cost['usd_total']:.4f} |"
    )


def render_markdown(report: Mapping[str, Any]) -> str:
    configurations = report["configurations"]
    lines = [
        "# Comparison of the 3 configurations (MEDDOCAN test)",
        "",
        "Entity-level, strict character span + category, micro-averaged.",
        "Model only and cascade on every test document; LLM only on a seeded sample.",
        "Latency is wall-clock per document on the evaluation machine, not on Lambda.",
        "Cost is Bedrock token usage times the list price; model only has no per-call cost.",
        "",
        "## Overall",
        "",
        "| Configuration | Documents | Recall | Precision | F1 | Latency p50 / p95 (s) "
        "| USD per document | USD total |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    lines += [_overall_row(name, configurations[name]) for name in CONFIGURATIONS]
    lines += ["", "## Recall per category", ""]
    done = [name for name in CONFIGURATIONS if configurations[name].get("status") == "done"]
    if done:
        lines += [
            "| Category | " + " | ".join(done) + " |",
            "| --- |" + " --- |" * len(done),
        ]
        for category in Category:
            cells = [
                f"{configurations[name]['per_category'][category.value]['recall']:.3f}"
                for name in done
            ]
            lines.append(f"| {category.value} | " + " | ".join(cells) + " |")
    else:
        lines.append("No configuration has been run yet.")
    lines += ["", ATTRIBUTION, ""]
    return "\n".join(lines)


def write_report(report: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write ``comparison.json`` and ``comparison.md`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{REPORT_NAME}.json"
    md_path = out_dir / f"{REPORT_NAME}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


# --- CLI (needs the model; ``llm_only`` and ``cascade`` need Bedrock) ---------


def _bedrock_client(read_timeout_s: int) -> BedrockRuntimeClient:
    import boto3
    from botocore.config import Config

    from clinical_deid.config import get_settings

    return boto3.client(
        "bedrock-runtime",
        region_name=get_settings().aws_region,
        config=Config(
            connect_timeout=2,
            read_timeout=read_timeout_s,
            retries={"total_max_attempts": 1, "mode": "standard"},
        ),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--corpus", type=Path, default=Path("data/meddocan"))
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--configs", nargs="+", choices=CONFIGURATIONS, default=["model_only"])
    parser.add_argument("--sample-size", type=int, default=LLM_ONLY_SAMPLE)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    from clinical_deid.config import get_settings

    settings = get_settings()
    documents = load_brat(args.corpus / "test" / "brat")
    needs_model = {"model_only", "cascade"} & set(args.configs)
    if needs_model and args.model_dir is None:
        parser.error("--model-dir is required for model_only and cascade")

    results: dict[str, dict[str, Any]] = {}
    detector = None
    if needs_model:
        from clinical_deid.adapters.hf_ner import HFEntityDetector

        detector = HFEntityDetector.from_pretrained(args.model_dir)
        detector.detect("Calentamiento.")  # Load lazily-initialised weights outside the timing.

    if "model_only" in args.configs:
        results["model_only"] = run_configuration(documents, detector.detect)

    if "cascade" in args.configs:
        from clinical_deid.adapters.bedrock_llm import READ_TIMEOUT_SECONDS, BedrockVerifier
        from clinical_deid.cascade import Cascade

        usage = UsageCountingClient(_bedrock_client(READ_TIMEOUT_SECONDS))
        cascade = Cascade(
            detector,
            BedrockVerifier(usage, settings.bedrock_model_id),
            threshold=settings.confidence_threshold,
            max_llm_calls=settings.max_llm_sentences,
        )
        results["cascade"] = run_configuration(
            documents, lambda text: cascade.run(text).entities, usage=usage
        )

    if "llm_only" in args.configs:
        from modeling.evaluation.llm_only import LLMOnlyExtractor

        usage = UsageCountingClient(_bedrock_client(LLM_ONLY_READ_TIMEOUT_S))
        extractor = LLMOnlyExtractor(usage, settings.bedrock_model_id)
        sample = sample_documents(documents, args.sample_size, args.seed)
        results["llm_only"] = run_configuration(sample, extractor.extract, usage=usage)

    for name, result in results.items():
        m = result["overall"]
        print(
            f"{name}: recall {m['recall']:.4f} precision {m['precision']:.4f} f1 {m['f1']:.4f} "
            f"({result['n_documents']} documents, {result['n_failures']} failures, "
            f"USD {result['cost']['usd_total']:.4f})"
        )

    previous_path = args.out_dir / f"{REPORT_NAME}.json"
    previous = (
        json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.exists() else None
    )
    meta = {
        "split": "test",
        "metric": "entity-level strict character span + category, micro-averaged",
        "llm_model_id": settings.bedrock_model_id,
        "prices_usd_per_million_tokens": PRICES,
        "cascade": {
            "threshold": settings.confidence_threshold,
            "max_llm_calls": settings.max_llm_sentences,
        },
        "llm_only_sample": {"size": args.sample_size, "seed": args.seed},
    }
    for path in write_report(merge_report(previous, results, meta), args.out_dir):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
