# Comparison of the 3 configurations (MEDDOCAN test)

Entity-level, strict character span + category, micro-averaged.
Model only and cascade on every test document; LLM only on a seeded sample.
Latency is wall-clock per document on the evaluation machine, not on Lambda.
Cost is Bedrock token usage times the list price; model only has no per-call cost.

## Overall

| Configuration | Documents | Recall | Precision | F1 | Latency p50 / p95 (s) | USD per document | USD total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| model_only | 250 | 0.896 | 0.881 | 0.888 | 1.36 / 2.25 | 0.00000 | 0.0000 |
| llm_only | pending | | | | | | |
| cascade | pending | | | | | | |

## Recall per category

| Category | model_only |
| --- | --- |
| NAME | 0.908 |
| DATE | 0.956 |
| LOCATION | 0.901 |
| ID | 0.719 |
| CONTACT | 0.975 |
| AGE | 0.977 |
| PROFESSION | 0.778 |
| OTHER | 0.917 |

Data: MEDDOCAN corpus (Marimon et al., 2019), licensed CC BY 4.0. MEDDOCAN contains clinical case reports with synthetic personal data; performance on real notes will likely be lower.
