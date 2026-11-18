"""Pydantic request/response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator

from clinical_deid.domain.categories import Category


class HealthResponse(BaseModel):
    """Service status. Contains no user data."""

    status: Literal["ok"]
    version: str


class DeidentifyRequest(BaseModel):
    """One clinical note (FR-01). The length limit is checked in the route (413)."""

    model_config = ConfigDict(extra="forbid")

    text: StrictStr

    @field_validator("text")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value


class EntityOut(BaseModel):
    """A masked span. The original value is deliberately not returned."""

    start: int
    end: int
    category: Category
    source: Literal["model", "llm"]


class Metrics(BaseModel):
    """Request metadata (NFR-02)."""

    latency_ms: int
    n_entities: int
    n_llm: int


class DeidentifyResponse(BaseModel):
    """De-identified note (FR-03)."""

    deidentified_text: str
    entities: list[EntityOut]
    metrics: Metrics
