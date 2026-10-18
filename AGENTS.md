# AGENTS.md — Cascade clinical de-identification (TFM)

Instructions for any coding agent (Claude Code, Copilot, CodeRabbit…).

## Language
- **Everything written to the repository is in English:** code, identifiers, comments, docstrings, docs, specs, ADRs, commit messages, issues, PR descriptions and UI text.
- The author chats in **Spanish**: reply to him in Spanish in the conversation, but write every file, commit and issue in English.
- Exception: Spanish sample clinical text used as test data or demo input stays in Spanish.

## Project
A web tool that de-identifies a Spanish clinical note: an in-house NER model (RoBERTa fine-tuned on
MEDDOCAN) + an LLM on Amazon Bedrock only for uncertain entities. Deployed on AWS Lambda.
Final project (TFM) of the Master's in AI-Assisted Development (BIG school). Due **23 Nov 2026**.

## Spec Driven Development — mandatory
1. Before implementing, read `specs/requirements.md` → `specs/design.md` → `specs/tasks.md`.
2. Implement **only** tasks that exist in `specs/tasks.md` (and their GitHub issue). If a task is missing or a spec is ambiguous or contradictory, **stop and ask**. Do not invent requirements.
3. Respect statuses: **DECIDED** is not changed without permission; **PROPOSED** is not implemented as final; **PENDING** is not implemented.
4. A scope or architecture change needs a new ADR in `docs/adr/` and a spec update. `docs/feasibility.md` is frozen: do not edit it.

## Commands
- Install: `uv sync`
- Tests: `uv run pytest`
- Lint and format: `uv run ruff check . --fix` and `uv run ruff format .`
- Local API: `uv run uvicorn clinical_deid.api.app:app --reload --port 8000`
- GitHub backlog (dry run): `uv run python scripts/github_backlog.py --dry-run`
- Hours: `uv run python scripts/hours.py status`

## Architecture (lightweight ports and adapters)
- `src/clinical_deid/domain/` imports nothing external (no transformers, boto3 or fastapi).
- `cascade.py` depends only on `domain/` and the protocols in `ports.py`.
- Hugging Face, Bedrock and FastAPI live in `adapters/` and `api/`.
- Cascade tests use `adapters/fakes.py`: they **never** call Bedrock or download models.

## Definition of done for a task
- New or updated tests pass; `ruff check` is clean.
- The task's "Done when" criterion is met and verified.
- Small commit formatted as `type(scope): description` (`feat`, `fix`, `test`, `docs`, `chore`, `ci`, `refactor`) referencing the issue (`#12`).

## Hard constraints
- **Public repository.** Never commit secrets, `.env`, tokens, patient data, model weights or the corpus.
- **Public sources only:** no private or proprietary data, code or knowledge.
- **Privacy by design:** user text is never stored or written to logs; metadata only.
- Only the sentence containing the uncertain entity is sent to the LLM; never the document.
- LLM output is schema-validated; on failure the entity is masked (fail-safe).
- In the frontend, data always goes through `textContent`, never `innerHTML`.
- Single AWS region: `eu-west-1`. Do not create AWS resources outside the plan in `specs/design.md`.

## Environment
- Development on GitHub Codespaces (no GPU). Training on Colab with notebooks that clone the repo.
- Python 3.11, `uv` package manager.
