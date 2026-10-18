---
name: security-review
description: Reviews changes or code against the project's security checklist (OWASP Web, OWASP LLM, privacy). Use before a PR that touches the API, login, cascade, frontend, Dockerfile or workflows.
argument-hint: "[optional base branch or path; defaults to changes against main]"
context: fork
agent: general-purpose
allowed-tools: Read Grep Glob Bash(git diff *) Bash(git log *) Bash(uv run pytest *)
---

# Security review of the de-identification tool

Scope: `$ARGUMENTS` (if empty, the changes in `git diff main...HEAD`; if there are none, all of `src/`).
Read `specs/design.md` §8 before starting. Do not modify files: report only. Write the report in English.

## Checklist
**OWASP LLM (2025 edition)**
- [ ] LLM01 Prompt injection: the sentence is delimited as data; the system prompt is fixed; the LLM only confirms/rejects.
- [ ] Improper output handling: response validated with a Pydantic schema; out of schema → the entity is masked.
- [ ] LLM10 Unbounded consumption: 10,000-character limit, at most N sentences, Bedrock timeout, low `max_tokens`.
- [ ] Only the sentence is sent, never the document.

**Web / API**
- [ ] XSS: the frontend uses `textContent`; no `innerHTML` with data; CSP present.
- [ ] Authentication: hashed password, signed `HttpOnly`/`Secure`/`SameSite=Strict` cookie, attempt limit, generic error message, 401 on protected routes.
- [ ] Input validation with Pydantic; errors without internal traces.

**Privacy**
- [ ] No log, exception or metric contains user text, sentences or LLM responses.
- [ ] Nothing is written to disk or a database.

**Supply chain and secrets**
- [ ] No secrets in code, Dockerfile, workflows or recent history.
- [ ] Pinned model revision; weights in safetensors; dependencies with a lockfile; Dependabot active.
- [ ] Least-privilege IAM: the Lambda only invokes the specific Bedrock model.

## Output
A table with: control · status (✅ / ⚠️ / ❌) · evidence (file:line) · proposed action.
End with the 3 most important findings and any missing security tests (`-m security`).
