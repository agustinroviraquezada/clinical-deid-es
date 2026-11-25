"""Static checks on the IAM policy files in infra/iam (design §8, T3.5)."""

import json
from pathlib import Path

import pytest

from clinical_deid.config import Settings

IAM = Path(__file__).resolve().parents[1] / "infra" / "iam"
BEDROCK_POLICY = IAM / "lambda-bedrock-policy.json"


def _statements() -> list[dict]:
    return json.loads(BEDROCK_POLICY.read_text(encoding="utf-8"))["Statement"]


def _as_list(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else value


@pytest.mark.security
def test_lambda_can_only_invoke_bedrock_models():
    for statement in _statements():
        assert statement["Effect"] == "Allow"
        assert _as_list(statement["Action"]) == ["bedrock:InvokeModel"]


@pytest.mark.security
def test_lambda_bedrock_resources_have_no_wildcards():
    for statement in _statements():
        for resource in _as_list(statement["Resource"]):
            assert "*" not in resource


@pytest.mark.security
def test_lambda_bedrock_resources_are_the_configured_model_in_eu_regions_only():
    model_id = Settings().bedrock_model_id  # eu.anthropic.claude-haiku-4-5-...
    base_model = model_id.removeprefix("eu.")
    resources = [r for s in _statements() for r in _as_list(s["Resource"])]

    assert f"arn:aws:bedrock:eu-west-1:ACCOUNT_ID:inference-profile/{model_id}" in resources
    for resource in resources:
        region = resource.split(":")[3]
        assert region.startswith("eu-")
        assert resource.endswith(f"/{model_id}") or resource.endswith(f"/{base_model}")


@pytest.mark.security
def test_foundation_models_are_reachable_only_through_the_eu_profile():
    """Direct calls to the foundation model (bypassing the EU profile) are not allowed."""
    for statement in _statements():
        resources = _as_list(statement["Resource"])
        if any(":foundation-model/" in r for r in resources):
            condition = statement["Condition"]["StringEquals"]
            assert condition["bedrock:InferenceProfileArn"].endswith(
                f"inference-profile/{Settings().bedrock_model_id}"
            )
