# ADR-0010 · Submission deadline moved to 29 Nov 2026

- **Status:** Accepted (2026-11-23)

## Context
The feasibility study (frozen) fixed the due date at 23 Nov 2026 and planned submission on
21 Nov, two days early, with public access opened on 20 Nov. On 23 Nov the school moved the
deadline to **29 Nov 2026**. At that point 28 h were logged and the remaining planned tasks
(T3.3–T5.4) add up to about 28 h, so the original dates could no longer be met.

## Decision
Keep the "submit with margin" rule and shift the final milestones: public access opened and
tested on **27 Nov**, submission on **28 Nov**, one day before the new deadline. Scope, task list,
hour budget (60 h ceiling, 65 h hard limit) and earlier checkpoints are unchanged.

## Alternatives considered
- Submit on 29 Nov itself · no margin for a failed upload or a last-minute AWS issue.
- Keep 21 Nov · already in the past.

## Consequences
- Updated: `AGENTS.md`, `scripts/hours.py` (`SUBMISSION`), `specs/tasks.md` (week 5 milestone and
  T5.4), `specs/design.md` §9 lifecycle, `docs/workflow.md`, `docs/deployment.md`.
- `docs/feasibility.md` keeps the original dates (frozen record).
- Six days remain for about 28 planned hours; the week-by-week plan in `hours.py` still ends at
  week 5 and is now only a reference.
