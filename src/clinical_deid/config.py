"""Validated settings read from environment variables (design §10)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Runtime configuration. Each field maps to the upper-case environment variable."""

    model_path: Path = Path("/opt/model")
    max_characters: int = Field(default=10_000, gt=0)
    # Both chosen on MEDDOCAN dev in T3.1 (ADR-0009, report api/report/threshold_dev.md).
    confidence_threshold: float = Field(default=0.96, ge=0.0, le=1.0)
    max_llm_sentences: int = Field(default=8, ge=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Settings for this process, read once."""
    return Settings()
