---
paths:
  - "src/**/*.py"
---

# Architecture rules (src/)

- Respect the dependency rule: `domain` ← `cascade` ← `adapters` / `api`. Never the other way round.
- `domain/` and `cascade.py` do not import `transformers`, `torch`, `boto3`, `fastapi` or `httpx`.
- A new external integration = a new adapter implementing a protocol from `ports.py`.
- Configuration only through `config.py` (pydantic-settings). No scattered `os.environ`.
- Type hints on every public function; dataclasses or Pydantic for structures.
- English identifiers, comments and docstrings.
- Never log user text, sentences sent to the LLM or LLM responses. Metadata only (lengths, counts, latencies).
- LLM or validation errors → fail-safe: the entity is masked.
- Every new core function gets its test in `tests/`.
