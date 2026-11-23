# ADR-0009 · Cascade threshold from per-band precision on dev

- **Status:** Accepted (2026-11-19)

## Context
Design §3 chose the cascade threshold as "the one that maximises recall with precision ≥ 0.85"
on MEDDOCAN dev. T3.1 measured the fine-tuned model with the product NER adapter on the 250 dev
documents (character offsets, strict span + type): model-only precision 0.877, recall 0.885.
Precision of the accepted entities is ≥ 0.85 at every threshold, so the rule as written always
gives t = 0 and the LLM would never be called. A cumulative variant (highest t whose uncertain
bucket, confidence < t, has precision < 0.85) fails the other way: the many wrong
low-confidence entities keep the bucket below 0.85 even at t = 0.99, so it always picks the top
of the grid (a third of all entities sent to the LLM).

## Decision
Entities are grouped into confidence bands between consecutive candidate thresholds
(0.30–0.90 in steps of 0.05, then 0.91–1.00 in steps of 0.01). The threshold is the upper edge
of the highest non-empty band whose precision is < 0.85. On dev this is **t = 0.96**: every band
below 0.96 has precision 0.04–0.79 and every band from 0.96 has 0.87–0.99. **N = 8** is the
95th percentile of uncertain entities per document at that threshold (median 4, max 16; 17 % of
entities are uncertain). Both values are defaults in `config.py`; the analysis is
`modeling/evaluation/threshold.py` and the report `src/clinical_deid/api/report/threshold_dev.md`.

## Alternatives considered
Literal design rule · t = 0, the cascade adds nothing. Cumulative bucket rule · t = 0.99, N = 13,
twice the LLM calls and latency at risk for NFR-03. Fixed budget t = 0.90, N = 6 · leaves the
0.90–0.96 bands (precision 0.66–0.79) unchecked.

## Consequences
The LLM sees only the bands where the model is wrong often enough to justify the call, with a
bounded number of calls per document. Bands are coarse below 0.90 and the rule is chosen once on
dev, so the value is not re-tuned on test. Documents with more than 8 uncertain entities mask the
rest by default (FR-07). The analysis also found and fixed an adapter bug (the HF pipeline only
treats `" "` as a word boundary, so entities swallowed the word after a line break); the
character-level numbers are therefore lower than the BIO-token numbers of T2.4.
