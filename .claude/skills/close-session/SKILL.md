---
name: close-session
description: Closes a TFM work session by logging hours, progress, blockers and next step in the hours log and the GitHub issue. Only when the author invokes it.
disable-model-invocation: true
argument-hint: "[hours spent] [optional task id or issue number]"
allowed-tools: Bash(git status *) Bash(git log *) Bash(uv run python scripts/hours.py *)
---

# Close session

Arguments: `$ARGUMENTS` (hours first, e.g. `1.5`; then, optionally, the task or issue).
If the hours are missing, ask for them. Do not estimate them yourself.
Talk to the author in Spanish; write the log entry and the issue comment in English.

## Current state
- Branch and changes: !`git status --short --branch`
- Latest commits: !`git log --oneline -8`
- Hours so far: !`uv run python scripts/hours.py total`

## Steps
1. Summarise the session in at most 3 bullets: done, blockers, next step. Use the commits and the conversation; do not invent.
2. Log the session (adds a row to the CSV):
   `uv run python scripts/hours.py log --hours <h> --task <Tn.m> --summary "<one line>"`
3. If there is an associated issue, propose this comment and post it with `gh issue comment <n> --body-file -` only if the author approves:
   ```
   **Session <date>** · <h> h
   - Done: …
   - Blockers: …
   - Next: …
   ```
   If the task's "Done when" is met, propose closing it (`gh issue close`).
4. Show the output of `uv run python scripts/hours.py status`: hours so far, current week, deviation from the plan, and warnings for the 6 Nov rule (≤ 36 h) and the 60 h ceiling.
5. If there are uncommitted changes, point it out. Do not push without permission.
