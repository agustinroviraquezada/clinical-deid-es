from fastapi.testclient import TestClient

import clinical_deid
from clinical_deid.api.app import app

client = TestClient(app)


def test_health_returns_ok_and_version():
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": clinical_deid.__version__}
