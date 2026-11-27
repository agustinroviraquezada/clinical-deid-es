# Synthetic demo notes: precomputed results

Synthetic demo notes written with an LLM and reviewed by hand; all personal data are invented. Scores use strict character span + category on a handful of notes: they illustrate behaviour on other styles, they are not a benchmark.

Cascade threshold: 0.96. Cascade and LLM only: pending (Bedrock).

| Note | Style | Gold | TP | FP | FN | Uncertain |
| --- | --- | --- | --- | --- | --- | --- |
| synthetic-progress-note | progress note | 9 | 5 | 4 | 4 | 3 |
| synthetic-emergency-abbreviations | abbreviations | 10 | 5 | 2 | 5 | 3 |
| synthetic-discharge-report | discharge report | 17 | 13 | 1 | 4 | 2 |
| synthetic-nursing-note | nursing note | 7 | 5 | 2 | 2 | 3 |
| synthetic-referral-letter | referral letter | 13 | 10 | 5 | 3 | 6 |

Model only, all notes: precision 0.731, recall 0.679, F1 0.704.
