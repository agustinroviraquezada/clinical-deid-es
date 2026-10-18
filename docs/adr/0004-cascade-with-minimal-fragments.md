# ADR-0004 · Cascade with minimal fragments and fail-safe

- **Status:** Accepted · 17 Oct 2026

## Context
The use case is de-identifying before using a third-party LLM, yet the cascade consults an LLM precisely on the most uncertain cases.

## Decision
Only the sentence containing the uncertain entity is sent to the LLM (confidence = mean token probability < threshold set on dev), at most N per document. The LLM only confirms or rejects and assigns a category. Any failure → the entity is masked. Provider: Bedrock with an EU profile.

## Alternatives considered
Whole document to the LLM: maximum exposure. Self-hosted LLM: +8–12 h and server cost.

## Consequences
Minimal, explainable exposure. Accepted limitation: a sentence with personal data leaves the system towards a third party.
