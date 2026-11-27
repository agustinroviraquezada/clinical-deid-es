"""Web interface (T4.1): page, static assets, examples and the Comparison data."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clinical_deid.api.app import REPORT_DIR, STATIC_DIR, app
from clinical_deid.api.auth import require_session

client = TestClient(app)


@pytest.fixture
def logged_in():
    """Skip the login, which is covered in test_auth.py."""
    app.dependency_overrides[require_session] = lambda: None
    yield
    app.dependency_overrides.pop(require_session, None)


def test_index_page_has_privacy_notice_and_attribution():
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    page = response.text
    assert 'id="privacy-notice"' in page
    assert "MEDDOCAN" in page
    assert "CC BY 4.0" in page


@pytest.mark.parametrize("asset", ["app.js", "styles.css", "examples.json"])
def test_static_assets_are_served(asset):
    assert client.get(f"/static/{asset}").status_code == 200


def test_comparison_returns_the_precomputed_report(logged_in):
    response = client.get("/api/comparison")

    assert response.status_code == 200
    expected = json.loads((REPORT_DIR / "comparison.json").read_text(encoding="utf-8"))
    assert response.json() == expected


def test_examples_fit_the_input_limit_and_carry_their_source():
    examples = json.loads((STATIC_DIR / "examples.json").read_text(encoding="utf-8"))

    assert 2 <= len(examples) <= 10
    for example in examples:
        assert {"id", "title", "source", "text"} <= example.keys()
        assert example["source"] in {"meddocan", "synthetic"}
        assert 0 < len(example["text"]) <= 10_000


@pytest.mark.security
@pytest.mark.parametrize("name", ["app.js", "index.html"])
def test_frontend_never_writes_html_from_data(name):
    source = (STATIC_DIR / name).read_text(encoding="utf-8")

    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert sink not in source, f"{sink} found in {name}"


@pytest.mark.security
@pytest.mark.parametrize("name", ["app.js", "index.html", "styles.css"])
def test_frontend_loads_nothing_from_other_origins(name):
    source = (STATIC_DIR / name).read_text(encoding="utf-8")

    # Plain <a href> links are fine; anything the browser loads must be same-origin.
    assert not re.search(r"src\s*=\s*[\"']?(https?:)?//", source)
    assert not re.search(r"<link[^>]+href\s*=\s*[\"']?(https?:)?//", source)
    assert not re.search(r"url\(\s*[\"']?(https?:)?//", source)
    assert not re.search(r"fetch\(\s*[\"'`](https?:)?//", source)
    assert "@import" not in source


def test_static_dir_lives_inside_the_package():
    # The Dockerfile copies src/clinical_deid only, so the page must live there.
    assert Path(STATIC_DIR).is_relative_to(Path(__file__).parents[1] / "src" / "clinical_deid")
