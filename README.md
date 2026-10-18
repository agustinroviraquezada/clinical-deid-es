# clinical-deid-es

> **Work in progress** · Final project (TFM) of the Master's in AI-Assisted Development (BIG school).

A web tool that removes personal data from a Spanish clinical note before it is used with a
third-party LLM. An in-house model (clinical RoBERTa fine-tuned on MEDDOCAN) detects personal data;
only uncertain cases are sent to an LLM, and only the affected sentence.

## Description
Coming soon (see `specs/requirements.md`).

## Tech stack
Python 3.11 · FastAPI · Hugging Face Transformers · Amazon Bedrock (Claude Haiku 4.5) ·
AWS Lambda (container image) · Docker · GitHub Actions · uv · pytest · ruff.
Details in `specs/design.md`.

## Installation and running
1. Open the repository in GitHub Codespaces (*Code → Codespaces → Create codespace*); the environment sets itself up.
2. `uv sync`
3. `uv run pytest`

## Project structure
```
.claude/        Claude Code configuration: permissions, rules and skills
.devcontainer/  Development environment (Codespaces)
docs/           Feasibility report (frozen), ADRs, workflow, hours log
scripts/        GitHub backlog and hours log
specs/          Spec Driven Development: requirements, design and tasks
src/            Application code
tests/          Tests
AGENTS.md       Instructions for coding agents
```

## Main features
Coming soon.

## Test access
- Username: coming soon
- Password: coming soon

## Links
- Deployment: coming soon
- Slides: coming soon
- Video: coming soon

## Data and attribution
Trained and evaluated on the **MEDDOCAN** corpus (Barcelona Supercomputing Center, CNIO and Hospital
12 de Octubre; Plan TL), licensed CC BY 4.0. Marimon et al., *Automatic De-identification of Medical
Texts in Spanish: the MEDDOCAN Track, Corpus, Guidelines, Methods and Evaluation of Results*,
IberLEF@SEPLN 2019, pp. 618–638. [doi:10.5281/zenodo.4279323](https://doi.org/10.5281/zenodo.4279323)

Base model: [`BSC-LT/roberta-base-biomedical-clinical-es`](https://huggingface.co/BSC-LT/roberta-base-biomedical-clinical-es) (Apache-2.0).

## Licence
Code under the [MIT](LICENSE). See [LICENCE](LICENCE) for third-party attributions.

## Disclaimer
Academic project. Not a certified system for real health data.
