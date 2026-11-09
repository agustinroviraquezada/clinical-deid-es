"""Pydantic request/response models."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Service status. Contains no user data."""

    status: Literal["ok"]
    version: str
