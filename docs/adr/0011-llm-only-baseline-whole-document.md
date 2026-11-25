# ADR-0011 · "LLM only" baseline reads whole MEDDOCAN documents, offline only

- **Status:** Accepted

## Context
AC-05 asks for a comparison of three configurations, one of them "LLM only" (requirements §7:
50 test documents). The design never defined how it works: the product port `LLMVerifier` only
confirms or rejects one entity, so it cannot find entities by itself. Finding them needs the LLM
to read the whole document, which the product forbids (FR-06: only the sentence of an uncertain
entity goes to the LLM, never the document). The feasibility cost estimate already assumed
"document + instructions" for this baseline.

## Decision
"LLM only" is an offline evaluation baseline in `modeling/evaluation/llm_only.py`: the LLM
receives one whole MEDDOCAN test document, delimited as data, and returns the text and category of
each entity as schema-validated JSON; every occurrence of each text is masked. It runs only on
MEDDOCAN (synthetic personal data), only from the evaluation script, and is never deployed
(ADR-0007). FR-06 still holds for the product without exceptions.

## Alternatives considered
- Send sentence by sentence: closer to FR-06, but ~15 calls per document multiply cost and latency
  and it is no longer the "LLM alone" baseline the comparison needs.
- Drop the "LLM only" configuration: AC-05 and FR-11 require three configurations.
- Ask the LLM for character offsets: LLMs count characters unreliably; locating the returned text
  is more robust.

## Consequences
- The comparison is complete and honest about the trade-off: cost and latency of reading whole
  documents versus the cascade's minimal fragments.
- Masking every occurrence of a returned text can add false positives (e.g. a common word); this
  is part of the baseline's measured behaviour.
- Risk: someone reuses this code in the product. Mitigated by its location in `modeling/` (never
  imported by `src/`, checked by `tests/test_architecture.py`) and this ADR.
