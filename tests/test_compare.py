"""Comparison of the 3 configurations: model only, LLM only and cascade (AC-05, task T3.4).

No model, corpus or Bedrock: fake detectors, verifiers and clients stand in for them, and the
documents are invented Spanish snippets.
"""

import json

import pytest

from clinical_deid.adapters.fakes import FakeDetector, FakeVerifier
from clinical_deid.cascade import Cascade
from clinical_deid.domain.categories import Category, category_for
from clinical_deid.domain.entities import Entity, Verdict
from modeling.evaluation.compare import (
    ATTRIBUTION,
    CONFIGURATIONS,
    UsageCountingClient,
    cost_summary,
    latency_stats,
    merge_report,
    render_markdown,
    run_configuration,
    sample_documents,
    score_spans,
    write_report,
)

TEXT = "Paciente Juan Pérez, de 54 años."
NAME = (9, 19, "NOMBRE_SUJETO_ASISTENCIA")
AGE = (24, 31, "EDAD_SUJETO_ASISTENCIA")
DOCS = [("doc-1", TEXT, {NAME, AGE})]


def _entity(span: tuple[int, int, str], confidence: float = 0.99) -> Entity:
    start, end, type_ = span
    return Entity(start, end, type_, category_for(type_), TEXT[start:end], confidence)


class FakeClock:
    """Advances 0.5 s per call: each document (two calls) takes exactly 0.5 s."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 0.5
        return self.now


class FakeBedrockClient:
    def __init__(self, result: dict | Exception) -> None:
        self._result = result

    def converse(self, **kwargs: object) -> dict:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


# --- score_spans -------------------------------------------------------------


def test_exact_span_and_category_is_a_true_positive():
    result = score_spans([{NAME, AGE}], [[_entity(NAME), _entity(AGE)]])

    assert result["overall"]["recall"] == 1.0
    assert result["overall"]["precision"] == 1.0
    assert result["per_category"]["NAME"]["tp"] == 1


def test_matching_is_on_category_not_meddocan_type():
    # The cascade may relabel an entity with a category; the type no longer matters.
    relabelled = Entity(9, 19, "NOMBRE_PERSONAL_SANITARIO", Category.NAME, "Juan Pérez", 0.5)

    result = score_spans([{NAME}], [[relabelled]])

    assert result["overall"]["tp"] == 1


def test_wrong_boundary_is_a_false_positive_and_a_false_negative():
    result = score_spans([{NAME}], [[_entity((9, 13, NAME[2]))]])

    assert (result["overall"]["tp"], result["overall"]["fp"], result["overall"]["fn"]) == (0, 1, 1)


def test_document_without_entities_scores_zero_without_error():
    result = score_spans([set()], [[]])

    assert result["overall"]["support"] == 0
    assert result["overall"]["f1"] == 0.0


def test_score_spans_rejects_mismatched_document_counts():
    with pytest.raises(ValueError):
        score_spans([set()], [])


# --- Usage, cost, latency and sample -----------------------------------------


def test_usage_counting_client_sums_tokens_across_calls():
    reply = {"usage": {"inputTokens": 300, "outputTokens": 20}}
    client = UsageCountingClient(FakeBedrockClient(reply))

    client.converse(modelId="m")
    client.converse(modelId="m")

    assert (client.calls, client.input_tokens, client.output_tokens) == (2, 600, 40)


def test_usage_counting_client_counts_failed_calls_and_reraises():
    client = UsageCountingClient(FakeBedrockClient(RuntimeError("throttled")))

    with pytest.raises(RuntimeError):
        client.converse(modelId="m")

    assert (client.calls, client.input_tokens) == (1, 0)


def test_usage_counting_client_tolerates_missing_usage():
    client = UsageCountingClient(FakeBedrockClient({"output": {}}))

    client.converse(modelId="m")

    assert (client.calls, client.input_tokens, client.output_tokens) == (1, 0, 0)


def test_cost_is_tokens_times_price_per_million():
    client = UsageCountingClient(FakeBedrockClient({}))
    client.input_tokens, client.output_tokens, client.calls = 1_000_000, 200_000, 10

    cost = cost_summary(client, n_documents=4, prices={"input": 1.0, "output": 5.0})

    assert cost["usd_total"] == pytest.approx(2.0)
    assert cost["usd_per_document"] == pytest.approx(0.5)
    assert cost["llm_calls"] == 10


def test_configuration_without_llm_costs_nothing():
    cost = cost_summary(None, n_documents=3)

    assert cost == {
        "llm_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "usd_total": 0.0,
        "usd_per_document": 0.0,
    }


def test_latency_stats_use_nearest_rank_percentiles():
    stats = latency_stats([float(s) for s in range(1, 21)])

    assert (stats["p50"], stats["p95"], stats["max"]) == (10.0, 19.0, 20.0)
    assert stats["mean"] == pytest.approx(10.5)


def test_latency_stats_of_no_documents_are_zero():
    assert latency_stats([]) == {"mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}


def test_sample_is_deterministic_and_of_the_requested_size():
    docs = [(f"doc-{i:03d}", "texto", set()) for i in range(250)]

    first = sample_documents(docs, 50, seed=7)

    assert len(first) == 50
    assert first == sample_documents(list(reversed(docs)), 50, seed=7)
    assert [d[0] for d in first] == sorted(d[0] for d in first)


def test_sample_larger_than_the_corpus_returns_every_document():
    docs = [("b", "t", set()), ("a", "t", set())]

    assert [d[0] for d in sample_documents(docs, 50, seed=7)] == ["a", "b"]


# --- run_configuration -------------------------------------------------------


def test_model_only_run_reports_scores_latency_and_zero_cost():
    detector = FakeDetector([_entity(NAME), _entity(AGE)])

    result = run_configuration(DOCS, detector.detect, clock=FakeClock())

    assert result["status"] == "done"
    assert result["n_documents"] == 1
    assert result["overall"]["recall"] == 1.0
    assert result["latency_s"]["p50"] == pytest.approx(0.5)
    assert result["cost"]["usd_total"] == 0.0


def test_failing_document_counts_as_missed_entities():
    def broken(text: str) -> list[Entity]:
        raise RuntimeError("LLM reply out of schema")

    result = run_configuration(DOCS, broken, clock=FakeClock())

    assert result["n_failures"] == 1
    assert result["overall"]["fn"] == 2
    assert result["overall"]["recall"] == 0.0


def test_cascade_run_drops_entities_the_llm_rejects():
    false_positive = Entity(0, 8, "PROFESION", Category.PROFESSION, "Paciente", 0.4)
    detector = FakeDetector([_entity(NAME), _entity(AGE), false_positive])
    verifier = FakeVerifier(Verdict(is_personal_data=False, category=Category.OTHER))
    cascade = Cascade(detector, verifier, threshold=0.9, max_llm_calls=8)

    result = run_configuration(DOCS, lambda text: cascade.run(text).entities, clock=FakeClock())

    assert result["overall"]["precision"] == 1.0
    assert result["overall"]["recall"] == 1.0
    assert len(verifier.calls) == 1


def test_run_records_llm_cost_from_the_counting_client():
    client = UsageCountingClient(
        FakeBedrockClient({"usage": {"inputTokens": 1_000, "outputTokens": 100}})
    )

    def predict(text: str) -> list[Entity]:
        client.converse(modelId="m")
        return []

    result = run_configuration(DOCS, predict, usage=client, clock=FakeClock())

    assert result["cost"]["llm_calls"] == 1
    assert result["cost"]["input_tokens"] == 1_000
    assert result["cost"]["usd_total"] > 0


# --- Report ------------------------------------------------------------------


def test_merge_keeps_previous_results_and_marks_missing_ones_pending():
    previous = {"configurations": {"llm_only": {"status": "done", "n_documents": 50}}}
    new = {"model_only": {"status": "done", "n_documents": 250}}

    report = merge_report(previous, new, meta={"split": "test"})

    assert set(report["configurations"]) == set(CONFIGURATIONS)
    assert report["configurations"]["model_only"]["n_documents"] == 250
    assert report["configurations"]["llm_only"]["n_documents"] == 50
    assert report["configurations"]["cascade"] == {"status": "pending"}
    assert report["split"] == "test"


def test_markdown_shows_pending_configurations_and_attribution():
    detector = FakeDetector([_entity(NAME)])
    report = merge_report(None, {"model_only": run_configuration(DOCS, detector.detect)}, meta={})

    markdown = render_markdown(report)

    assert "| model_only |" in markdown
    assert "| cascade | pending |" in markdown
    assert ATTRIBUTION in markdown


@pytest.mark.security
def test_report_holds_numbers_only_never_document_text(tmp_path):
    detector = FakeDetector([_entity(NAME), _entity(AGE)])
    report = merge_report(None, {"model_only": run_configuration(DOCS, detector.detect)}, meta={})

    json_path, md_path = write_report(report, tmp_path)

    for path in (json_path, md_path):
        content = path.read_text(encoding="utf-8")
        assert "Juan" not in content and "Pérez" not in content
    assert (
        json.loads(json_path.read_text(encoding="utf-8"))["configurations"]["model_only"]["status"]
        == "done"
    )
    assert json_path.name == "comparison.json" and md_path.name == "comparison.md"
