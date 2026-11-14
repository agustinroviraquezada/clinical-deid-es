# ADR-0007 · Offline model code grouped under `modeling/`

- **Status:** Accepted · 14 Nov 2026

## Context
The repository mixes two kinds of code: the product that runs on Lambda (`src/clinical_deid/`)
and offline tooling that produces what the product consumes (corpus preparation, fine-tuning,
evaluation). Design §2 listed `data_prep/` and `evaluation/` as separate root folders, and
fine-tuning (T2.3) would have added a third one. Training needs heavy dependencies (`torch`,
`datasets`, `seqeval`, `accelerate`) that must not reach the Lambda image.

## Decision
All offline model lifecycle code lives under a single root folder, `modeling/`, with the
sub-packages `data_prep/`, `training/` and `evaluation/`. `modeling/` may import
`src/clinical_deid`; `src/` never imports `modeling/` (enforced by a test in
`tests/test_architecture.py`). Training dependencies go in a separate `uv` dependency group.
Evaluation code lives in `modeling/evaluation/`, but the precomputed report the Comparison tab
serves is written to `src/clinical_deid/api/report/`, so the product never depends on a path
inside `modeling/`.

## Alternatives considered
- One root folder per concern (`data_prep/`, `training/`, `evaluation/`): clutters the root.
- Everything inside `src/clinical_deid/` with optional extras (Cookiecutter Data Science style):
  the separation becomes a convention only, and the Dockerfile would have to exclude
  sub-packages explicitly.
- Other names (`ml/`, `pipelines/`, `offline/`): `modeling/` was the author's choice.

## Consequences
One clear boundary between product and tooling; smaller image and attack surface. `modeling/` is
not an installable package: it runs from the repository root (tests add `.` to `pythonpath`;
the Colab notebook clones the repo and works from its root). Existing commands change from
`python -m data_prep...` to `python -m modeling.data_prep...`.
