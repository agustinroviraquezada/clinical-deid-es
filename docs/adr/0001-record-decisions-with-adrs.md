# ADR-0001 · Record decisions with ADRs

- **Status:** Accepted · 18 Oct 2026

## Context
The feasibility session (17–18 Oct) made more than 50 decisions, documented in `docs/feasibility.md`. That document is frozen, and new decisions need a home.

## Decision
Every new architecture or scope decision is recorded as a numbered ADR in `docs/adr/`. The specs (`specs/`) reflect the current state.

## Alternatives considered
Keeping the Claude Docs technical document alive: it duplicates the repo, drifts, and the agent cannot read it.

## Consequences
Versioned traceability next to the code; one short file per decision. Cost: the discipline of writing them.
