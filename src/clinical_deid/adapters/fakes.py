"""Test doubles for the ports: no network, no model, no cost."""

from clinical_deid.domain.entities import Entity, Verdict


class FakeDetector:
    """EntityDetector that returns a preset list of entities."""

    def __init__(self, entities: list[Entity]) -> None:
        self._entities = list(entities)

    def detect(self, text: str) -> list[Entity]:
        return list(self._entities)


class FakeVerifier:
    """LLMVerifier that returns a fixed verdict or raises a fixed exception."""

    def __init__(self, result: Verdict | Exception) -> None:
        self._result = result
        self.calls: list[tuple[str, Entity]] = []

    def verify(self, sentence: str, entity: Entity) -> Verdict:
        self.calls.append((sentence, entity))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result
