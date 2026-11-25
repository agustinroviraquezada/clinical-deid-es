import logging

import pytest
from fastapi.testclient import TestClient

import clinical_deid
from clinical_deid.adapters.disabled_llm import DisabledVerifier
from clinical_deid.adapters.fakes import FakeDetector, FakeVerifier
from clinical_deid.api.app import app, get_cascade
from clinical_deid.cascade import Cascade
from clinical_deid.domain.categories import Category
from clinical_deid.domain.entities import Entity, Verdict

NOTE = "Paciente Lucía Fernández, de 54 años, ingresó el 12/03/2025 en Teruel."

client = TestClient(app)


def _entity(text: str, fragment: str, category: Category, confidence: float = 0.99) -> Entity:
    start = text.index(fragment)
    return Entity(start, start + len(fragment), category.value, category, fragment, confidence)


@pytest.fixture
def entities() -> list[Entity]:
    return [
        _entity(NOTE, "Lucía Fernández", Category.NAME),
        _entity(NOTE, "12/03/2025", Category.DATE, confidence=0.4),
    ]


@pytest.fixture(autouse=True)
def fake_cascade(entities):
    """Replace the real model with a test double for every test in this module."""
    cascade = Cascade(FakeDetector(entities), DisabledVerifier(), threshold=0.85, max_llm_calls=0)
    app.dependency_overrides[get_cascade] = lambda: cascade
    yield
    app.dependency_overrides.clear()


def test_health_returns_ok_and_version():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": clinical_deid.__version__}


def test_deidentify_masks_entities_and_reports_metrics():
    response = client.post("/api/deidentify", json={"text": NOTE})

    assert response.status_code == 200
    body = response.json()
    assert body["deidentified_text"] == (
        "Paciente [NAME], de 54 años, ingresó el [DATE] en Teruel."
    )
    name, date = NOTE.index("Lucía Fernández"), NOTE.index("12/03/2025")
    assert body["entities"] == [
        {"start": name, "end": name + 15, "category": "NAME", "source": "model"},
        {"start": date, "end": date + 10, "category": "DATE", "source": "model"},
    ]
    assert body["metrics"]["n_entities"] == 2
    assert body["metrics"]["n_llm"] == 0
    assert body["metrics"]["latency_ms"] >= 0


def test_entity_confirmed_by_llm_is_reported_with_llm_source(entities):
    verifier = FakeVerifier(Verdict(is_personal_data=True, category=Category.DATE))
    cascade = Cascade(FakeDetector(entities), verifier, threshold=0.85)
    app.dependency_overrides[get_cascade] = lambda: cascade

    body = client.post("/api/deidentify", json={"text": NOTE}).json()

    assert [e["source"] for e in body["entities"]] == ["model", "llm"]
    assert body["metrics"]["n_llm"] == 1


def test_response_never_echoes_entity_text(entities):
    """The client only needs offsets and categories; the original values stay out."""
    body = client.post("/api/deidentify", json={"text": NOTE}).json()

    assert "Lucía" not in str(body)
    assert all(set(e) == {"start", "end", "category", "source"} for e in body["entities"])


@pytest.mark.parametrize("entities", [[]])
def test_text_at_the_limit_is_accepted():
    response = client.post("/api/deidentify", json={"text": "a" * 10_000})

    assert response.status_code == 200
    assert response.json()["deidentified_text"] == "a" * 10_000


@pytest.mark.parametrize("entities", [[]])
@pytest.mark.security
def test_text_over_the_limit_returns_413():
    response = client.post("/api/deidentify", json={"text": "a" * 10_001})

    assert response.status_code == 413
    assert "10000" in response.json()["detail"]


@pytest.mark.security
def test_oversized_text_is_rejected_before_loading_the_model():
    def model_must_not_load() -> Cascade:
        raise AssertionError("the model was loaded for an oversized request")

    app.dependency_overrides[get_cascade] = model_must_not_load

    response = client.post("/api/deidentify", json={"text": "a" * 10_001})

    assert response.status_code == 413


@pytest.mark.parametrize("payload", [{"text": ""}, {"text": "   "}, {}, {"text": 42}, {"x": "y"}])
def test_invalid_payload_returns_400_without_echoing_input(payload):
    response = client.post("/api/deidentify", json=payload)

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid request"}


@pytest.mark.security
def test_invalid_payload_does_not_echo_user_text():
    """FastAPI's default 422 body copies the rejected input; ours must not."""
    response = client.post("/api/deidentify", json={"text": ["Lucía Fernández"]})

    assert response.status_code == 400
    assert "Lucía" not in response.text


@pytest.mark.parametrize("entities", [[]])
@pytest.mark.security
def test_html_in_input_is_returned_as_plain_json_text():
    text = "Nota <script>alert(1)</script> sin datos."

    response = client.post("/api/deidentify", json={"text": text})

    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["deidentified_text"] == text


@pytest.mark.security
def test_logs_contain_metadata_but_never_the_text(caplog):
    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/deidentify", json={"text": NOTE})

    assert response.status_code == 200
    logged = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "Lucía" not in logged
    assert "Teruel" not in logged
    assert f"chars={len(NOTE)}" in logged
    assert "entities=2" in logged


class _StubVerifier:
    def verify(self, sentence: str, entity: Entity) -> Verdict:  # pragma: no cover - not called
        raise AssertionError("no LLM call expected while wiring")


@pytest.fixture
def wiring(monkeypatch):
    """Call the real get_cascade() with fake settings, a fake model and no AWS client."""
    from clinical_deid.adapters.bedrock_llm import BedrockVerifier
    from clinical_deid.adapters.hf_ner import HFEntityDetector
    from clinical_deid.api import app as app_module
    from clinical_deid.config import Settings

    detector = FakeDetector([])
    monkeypatch.setattr(HFEntityDetector, "from_pretrained", classmethod(lambda cls, p: detector))
    stub = _StubVerifier()
    monkeypatch.setattr(BedrockVerifier, "from_settings", classmethod(lambda cls: stub))

    def build(**overrides) -> Cascade:
        settings = Settings(**overrides)
        monkeypatch.setattr(app_module, "get_settings", lambda: settings)
        app_module.get_cascade.cache_clear()
        try:
            return app_module.get_cascade()
        finally:
            app_module.get_cascade.cache_clear()

    build.stub = stub
    return build


def test_cascade_is_model_only_when_llm_disabled(wiring):
    cascade = wiring(llm_enabled=False)

    assert isinstance(cascade._verifier, DisabledVerifier)
    assert cascade._max_llm_calls == 0


def test_cascade_uses_bedrock_with_cap_and_budget_when_llm_enabled(wiring):
    cascade = wiring(llm_enabled=True, max_llm_sentences=5, llm_time_budget_s=30)

    assert cascade._verifier is wiring.stub
    assert cascade._max_llm_calls == 5
    assert cascade._budget == 30


@pytest.mark.security
def test_logs_stay_metadata_only_when_the_llm_runs(caplog):
    """The LLM path (n_llm > 0) must not add the sentence or the verdict to the logs."""
    uncertain = [_entity(NOTE, "Teruel", Category.LOCATION, confidence=0.4)]
    verifier = FakeVerifier(Verdict(True, Category.LOCATION))
    cascade = Cascade(FakeDetector(uncertain), verifier, threshold=0.85, max_llm_calls=8)
    app.dependency_overrides[get_cascade] = lambda: cascade

    with caplog.at_level(logging.DEBUG):
        response = client.post("/api/deidentify", json={"text": NOTE})

    assert response.json()["metrics"]["n_llm"] == 1
    logged = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "Teruel" not in logged
    assert "Lucía" not in logged
    assert "n_llm=1" in logged
