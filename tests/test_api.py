import logging

import pytest
from fastapi.testclient import TestClient

import clinical_deid
from clinical_deid.adapters.disabled_llm import DisabledVerifier
from clinical_deid.adapters.fakes import FakeDetector
from clinical_deid.api.app import app, get_cascade
from clinical_deid.cascade import Cascade
from clinical_deid.domain.categories import Category
from clinical_deid.domain.entities import Entity

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
    cascade = Cascade(FakeDetector(entities), DisabledVerifier(), threshold=0.85)
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
