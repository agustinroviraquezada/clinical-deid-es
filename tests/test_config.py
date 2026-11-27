from pathlib import Path

import pytest
from pydantic import ValidationError

from clinical_deid.config import Settings


def test_defaults_match_design(monkeypatch):
    for name in ("MODEL_PATH", "MAX_CHARACTERS", "CONFIDENCE_THRESHOLD", "MAX_LLM_SENTENCES"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.model_path == Path("/opt/model")
    assert settings.max_characters == 10_000
    # Chosen on MEDDOCAN dev in T3.1 (ADR-0009).
    assert settings.confidence_threshold == 0.96
    assert settings.max_llm_sentences == 8


def test_bedrock_defaults_match_design(monkeypatch):
    for name in ("BEDROCK_MODEL_ID", "AWS_REGION"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.bedrock_model_id == "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    assert settings.aws_region == "eu-west-1"


def test_environment_variables_override_defaults(monkeypatch):
    monkeypatch.setenv("MODEL_PATH", "/srv/model")
    monkeypatch.setenv("MAX_CHARACTERS", "500")
    monkeypatch.setenv("CONFIDENCE_THRESHOLD", "0.5")
    monkeypatch.setenv("MAX_LLM_SENTENCES", "3")

    settings = Settings()

    assert settings.model_path == Path("/srv/model")
    assert settings.max_characters == 500
    assert settings.confidence_threshold == 0.5
    assert settings.max_llm_sentences == 3


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("CONFIDENCE_THRESHOLD", "1.5"),
        ("CONFIDENCE_THRESHOLD", "-0.1"),
        ("MAX_CHARACTERS", "0"),
        ("MAX_LLM_SENTENCES", "-1"),
    ],
)
def test_out_of_range_values_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValidationError):
        Settings()


def test_llm_is_off_by_default_with_a_budget_under_the_lambda_timeout(monkeypatch):
    for name in ("LLM_ENABLED", "LLM_TIME_BUDGET_S"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.llm_enabled is False
    # Worst case is budget + one call (2 s connect + 10 s read) + a cold start: well under 120 s.
    assert settings.llm_time_budget_s == 45.0


def test_llm_settings_read_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_TIME_BUDGET_S", "20")

    settings = Settings()

    assert settings.llm_enabled is True
    assert settings.llm_time_budget_s == 20.0


@pytest.mark.parametrize("value", ["0", "-5", "100"])
def test_llm_time_budget_out_of_range_is_rejected(monkeypatch, value):
    monkeypatch.setenv("LLM_TIME_BUDGET_S", value)

    with pytest.raises(ValidationError):
        Settings()


def test_login_secrets_are_unset_by_default(monkeypatch):
    for name in ("DEMO_USERNAME", "DEMO_PASSWORD_HASH", "SESSION_SECRET"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.demo_username == "demo"
    # No default secrets: without them every login fails (fail closed, ADR-0006).
    assert settings.demo_password_hash is None
    assert settings.session_secret is None
