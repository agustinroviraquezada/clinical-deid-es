"""Ports the cascade depends on (design §2). Adapters implement them."""

from typing import Protocol

from clinical_deid.domain.entities import Entity, Verdict


class EntityDetector(Protocol):
    """Detects personal-data entities in a document."""

    def detect(self, text: str) -> list[Entity]:
        """Return entities with confidence in [0, 1]."""
        ...


class LLMVerifier(Protocol):
    """Confirms or rejects an uncertain entity given only its sentence."""

    def verify(self, sentence: str, entity: Entity) -> Verdict:
        """Return the verdict; raise on timeout, error or out-of-schema output."""
        ...
