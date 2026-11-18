from pathlib import Path

import pytest
from pydantic import ValidationError

from clinical_deid.config import Settings


def test_defaults_match_design(monkeypatch):
    for name in ("MODEL_PATH", "MAX_CHARACTERS", "CONFIDENCE_THRESHOLD"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.model_path == Path("/opt/model")
    assert settings.max_characters == 10_000
    assert settings.confidence_threshold == 0.85


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("MODEL_PATH", "/srv/model")
    monkeypatch.setenv("MAX_CHARACTERS", "500")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.5")

    settings = Settings()

    assert settings.model_path == Path("/srv/model")
    assert settings.max_characters == 500
    assert settings.confidence_threshold == 0.5


@pytest.mark.parametrize(
    ("name", "value"),
    [("CONFIDENCE_THRESHOLD", "1.5"), ("CONFIDENCE_THRESHOLD", "-0.1"), ("MAX_CHARACTERS", "0")],
)
def test_out_of_range_values_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings()
