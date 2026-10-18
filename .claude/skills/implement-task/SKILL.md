---
name: implement-task
description: Implements a backlog task following Spec Driven Development (spec, plan, tests, code, verification). Use when the author asks to work on a task Tn.m or on a project issue.
argument-hint: "[task id, e.g. T1.3, or issue number]"
---

# Implement task with SDD: $ARGUMENTS

Talk to the author in Spanish; write code, tests, docs and commits in English.

## 1. Locate
- Find task `$ARGUMENTS` in `specs/tasks.md` (or the issue with `gh issue view`). If it does not exist, **stop and ask**.
- Read its `Spec` and `Done when` fields and the referenced sections of `specs/requirements.md` and `specs/design.md`.
- If anything you need is marked PENDING or PROPOSED, say so and ask before continuing.

## 2. Plan (and wait for approval)
Present, in fewer than 15 lines:
- Which files you will create or change.
- Which tests you will write first (cases: happy path, limit, fail-safe).
- Risks or open questions.
- Estimate versus the task's hours.
Wait for the author's "ok" before writing code.

## 3. Tests first
Write the tests and run them (`uv run pytest`) to see them fail for the right reason.

## 4. Implement
- Follow `AGENTS.md` and the rules in `.claude/rules/`.
- Minimal changes to meet "Done when". Nothing outside the task's scope.

## 5. Verify
- `uv run ruff check . --fix && uv run ruff format .`
- `uv run pytest`
- Check every item of "Done when" and state explicitly which one is met and how you verified it.

## 6. Close
- Propose a commit `type(scope): description (#issue)` and commit if the author approves.
- If the task reveals a scope or architecture change, propose an ADR in `docs/adr/`; do not change the spec on your own.
- If the task is complete, remind the author to run `/close-session <hours>`.
