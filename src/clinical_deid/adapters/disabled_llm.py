"""LLMVerifier used when the LLM is off (model-only mode, T2.6)."""

from clinical_deid.domain.entities import Entity, Verdict


class LLMDisabledError(RuntimeError):
    """Raised when verification is requested while the LLM is disabled."""


class DisabledVerifier:
    """Never calls an LLM. Raising makes the cascade apply its fail-safe: the entity is masked."""

    def verify(self, sentence: str, entity: Entity) -> Verdict:
        raise LLMDisabledError("LLM verification is disabled")
