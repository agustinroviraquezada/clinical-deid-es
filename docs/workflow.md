# Workflow

Where everything lives and how a work session runs.

## Document map

| What | Where | Who updates it |
| --- | --- | --- |
| Rationale behind the initial decisions | `docs/feasibility.md` (frozen) | Nobody |
| New decisions | `docs/adr/NNNN-*.md` | The author |
| Scope and acceptance criteria | `specs/requirements.md` | The author, with an ADR |
| Architecture | `specs/design.md` | The author, with an ADR if a decided item changes |
| Task plan | `specs/tasks.md` | When re-planning |
| **Live status** | GitHub Issues + Projects (milestone = week) | Every session |
| Actual hours | `docs/hours-log.csv` (`scripts/hours.py`) | `/close-session` |
| Agent instructions | `AGENTS.md` (+ `CLAUDE.md`, `.claude/`) | When a mistake repeats |



## A work session

1. Move the issue to *In progress*.
2. In Claude Code: `/implement-task T2.1` (plan → approval → tests → code → verification).
3. Before a PR touching the API, login, cascade, frontend, Dockerfile or workflows: `/security-review`.
4. When finished: `/close-session 1.5 T2.1` → logs hours, comments on the issue and shows status against the plan.
5. If scope or architecture changes: new ADR + spec update.

## Checkpoints

| Date | Checkpoint | If not met |
| --- | --- | --- |
| 23 Oct | "Hello world" deployed on Lambda | Week 2 starts with the deployment |
| 31 Oct | Recall ≥ 0.90 and precision ≥ 0.85 | Plan B: accept and document |
| 6 Nov | Cascade deployed and evaluated, and ≤ 36 h | The JSON extension becomes future work |
| 13 Nov | Feature freeze | Bug fixes only |
| 20 Nov | Public access open and tested | — |
| 21 Nov | Submission | — |

`uv run python scripts/hours.py status` shows where you stand.
