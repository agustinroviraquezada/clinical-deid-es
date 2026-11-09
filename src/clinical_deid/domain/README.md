# `domain/` — core concepts

Pure Python, **no external dependencies** (standard library only). Everything here can be
tested in milliseconds and knows nothing about models, LLMs or HTTP.

## Files

### `categories.py`
`Category` (`StrEnum`) — the 8 grouped categories shown in the output (FR-04):
`NAME, DATE, LOCATION, ID, CONTACT, AGE, PROFESSION, OTHER`.
The table that maps each original MEDDOCAN type to one of these categories is added in
**T2.2**, after inspecting the corpus.

### `entities.py`
Immutable value objects (`@dataclass(frozen=True, slots=True)`):

- `Entity(start, end, type, category, text, confidence)` — one detected span.
  `start`/`end` are character offsets (end exclusive), `type` is the original MEDDOCAN label,
  `category` the grouped one, `confidence` in [0, 1] (mean token probability, design §3).
- `Verdict(is_personal_data, category)` — what the LLM answers about an uncertain entity.

### `masker.py`
`mask(text, entities) -> str` replaces each span with `[CATEGORY]` (FR-03).

- Order of the input entities does not matter (they are sorted by offset).
- Raises `ValueError` for out-of-range or overlapping spans instead of producing corrupted text.

```python
mask("Paciente Lucía Fernández ingresa el 12/03/2025.", entities)
# -> "Paciente [NAME] ingresa el [DATE]."
```

## Rules
- No imports from `ports`, `cascade`, `adapters` or `api` (domain is the innermost layer).
- No logging of text.

Tests: `tests/test_masker.py`, `tests/test_architecture.py`.
