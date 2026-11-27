"""Validated settings read from environment variables (design §10)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration. Each field maps to the upper-case environment variable."""

    model_path: Path = Path("/opt/model")
    max_characters: int = Field(default=10_000, gt=0)
    # Both chosen on MEDDOCAN dev in T3.1 (ADR-0009, report api/report/threshold_dev.md).
    confidence_threshold: float = Field(default=0.96, ge=0.0, le=1.0)
    max_llm_sentences: int = Field(default=8, ge=0)
    # Off unless the deployment opts in, so nothing calls Bedrock by accident (T3.5).
    llm_enabled: bool = False
    # Wall-clock limit for the LLM calls of one request. Worst case is this plus one call
    # (2 s connect + 10 s read) plus a cold start, which must stay under the 120 s Lambda timeout.
    llm_time_budget_s: float = Field(default=45.0, gt=0, le=90)
    # LLM on Amazon Bedrock (design §4). Credentials come from the IAM role, never from here.
    bedrock_model_id: str = "eu.anthropic.claude-haiku-4-5-20251001-v1:0"
    aws_region: str = "eu-west-1"
    # Demo login (design §7, ADR-0006). Both secrets come from the Lambda environment, never
    # from the repo. If either is missing, every login fails (fail closed).
    demo_username: str = "demo"
    demo_password_hash: SecretStr | None = None
    session_secret: SecretStr | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings for this process, read once."""
    return Settings()
