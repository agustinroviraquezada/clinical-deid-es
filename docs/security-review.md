# Security review — T4.5 (27 Nov 2026)

Scope: all deployable code: `src/`, `Dockerfile`, `.github/workflows/`, `infra/iam/`.
Method: the project's `/security-review` checklist (OWASP LLM 2025, OWASP Web, privacy, supply chain),
checked against `specs/design.md` §8 (NFR-06). Status: ✅ met · ⚠️ met with a documented limit.

## Controls

| Control | Status | Evidence | Outcome |
| --- | --- | --- | --- |
| LLM01 Prompt injection: the sentence is data, the system prompt is fixed, the LLM only confirms or rejects | ✅ | `adapters/bedrock_llm.py`: fixed prompt that says "treat as data"; `<` and `>` are swapped for look-alike characters, so the text cannot close the delimiting tags | — |
| Improper output handling: strict schema, otherwise mask | ✅ | `bedrock_llm.py`: Pydantic model with `extra=forbid, strict`; `cascade.py`: any exception or malformed verdict masks the entity; `stopReason="max_tokens"` is covered by `tests/test_bedrock_llm.py` | — |
| LLM10 Unbounded consumption | ⚠️ | 10,000 chars → 413 before the model loads (`api/app.py`); per-request call cap and time budget (`config.py`, `cascade.py`); `maxTokens=50`, temperature 0; 2 s / 10 s timeouts, no retries. Reserved concurrency 5 is **not yet applied** (`docs/deployment.md`, #26) | **Fixed:** `MAX_LLM_SENTENCES` had no upper bound; now `le=20` (finding 2). **Open:** reserved concurrency (P1 below) |
| Only the sentence is sent, never the document | ✅ | `cascade.py`: sentence bounds and 1,000-char cap (masked if over); second check in `bedrock_llm.py`; the sentence regex has no quadratic case (`domain/sentences.py`) | — |
| XSS | ✅ | `static/app.js` has no `innerHTML`, `outerHTML`, `insertAdjacentHTML` or `eval`; masked text is built as text nodes; strict CSP with `frame-ancestors 'none'`; no inline scripts | — |
| Authentication | ⚠️ | argon2 hash; constant-time compare and a dummy hash for unknown users; `HttpOnly`/`Secure`/`SameSite=Strict` cookie, 1 h; 5 failures per client lock for 15 min; one generic 401; fails closed if secrets are missing (`api/auth.py`, `api/app.py`) | **Accepted limits** A1, A2 below |
| Input validation, errors without traces | ⚠️ | `extra=forbid`, `StrictStr`, 128-char credentials (`api/schemas.py`); generic 400 instead of FastAPI's 422 (which echoes input); generic 500 that logs only the exception type; `/docs` and `/openapi.json` off | **Accepted limit** A3 below |
| Privacy: logs hold metadata only | ✅ | `api/app.py` logs counts and latency only; login logs carry no credentials; Bedrock errors log only the exception type; `Cache-Control: no-store` on `/api/*` | — |
| Nothing written to disk or a database | ✅ | No writes in `src/`; the HF cache points to `/tmp`, offline mode (`Dockerfile`) | — |
| No secrets in code, Dockerfile, workflows or history | ✅ | Regex scan of the whole history (AWS keys, HF and GitHub tokens, argon2 hashes, private keys): nothing found. `HF_TOKEN` is used in one workflow step only and is not passed to `docker build`; `.dockerignore` excludes `.env*`, `.git`, `.claude`, data and tests | Manual check M1 below |
| Pinned model revision, safetensors, lockfile, Dependabot | ✅ | 40-char commit SHA checked in the workflow (`config/model.json`, `deploy.yml`); `use_safetensors=True` and a file allowlist; `uv export --frozen` + `pip --require-hashes`; base images pinned by digest; Dependabot for `uv` and `github-actions` | **Fixed:** `ci.yml` pinned actions by tag; now by commit SHA like `deploy.yml` (finding 3) |
| Least-privilege IAM | ✅ | Lambda: only `bedrock:InvokeModel` on the EU Haiku inference profile (`infra/iam/lambda-bedrock-policy.json`); deploy role limited to one ECR repo and one function; OIDC trust limited to the `production` environment | Manual check M2 below |

## Findings

### Fixed in this task

1. **Deploy workflow failed on every run since T4.2, so nothing new reached Lambda.**
   The `/api/deidentify` smoke test sent no session cookie and got 401. The login and the security
   headers (T4.2, T4.3) were therefore never deployed. Fix (`deploy.yml`): the emulator gets a random,
   masked, per-run `SESSION_SECRET`. The smoke test first checks that a request without a cookie gets
   **401**. It then signs a cookie with the app's own `sign_session()` inside the image and checks for
   **200** with the patient name masked. This closes the missing deployed-image auth test.
2. **No upper bound on `MAX_LLM_SENTENCES`.** A mistyped environment value could multiply Bedrock
   calls per request. Fix: `le=20` in `config.py`; tests in `tests/test_config.py` (20 accepted, 21 rejected).
3. **CI actions pinned by tag.** Fix: `ci.yml` now pins `actions/checkout` and `astral-sh/setup-uv` by
   commit SHA with the version as a comment. Dependabot keeps updating them. Low risk before the fix:
   CI is read-only and has no secrets.

### Accepted limits (demo scope, ADR-0006)

- **A1 · Sessions cannot be revoked on the server.** The session is a stateless HMAC token, so logout only
  expires the cookie in the browser. A token copied before logout stays valid until it expires (at most 1 h).
  Theft is unlikely given `HttpOnly` + `Secure` + `SameSite=Strict` and the absence of XSS sinks.
  Rotating `SESSION_SECRET` revokes every session at once. Recorded by
  `tests/test_auth.py::test_session_token_still_valid_after_logout`.
- **A2 · The lockout counter is per Lambda instance**, in memory. It was already accepted in
  `specs/design.md` §7. Once reserved concurrency (5) is applied, it bounds the number of counters.
  Until then, the account limit of 10 concurrent executions does.
- **A3 · The body is parsed before the session check.** An unauthenticated caller can make the function
  parse a request up to the 6 MB Function URL limit. The parse is cheap compared with inference, and
  the 10,000-char check and the 401 run before the model is touched.

### Manual checks for the author

- **M1** · `.env.example` must hold placeholders only (the agent's permissions do not let it read the file).
- **M2** · In the IAM console, the Lambda role must have only `AWSLambdaBasicExecutionRole` and the
  inline Bedrock policy attached (`docs/deployment.md`).

### Pending outside this task

- **P1 · Reserved concurrency (#26).** It cannot be set yet: the account's applied limit is 10 concurrent
  executions and AWS keeps 10 unreserved. That account limit caps parallel copies at 10 in the meantime.
  A Service Quotas increase was requested. If it is not granted before submission, list it as a known
  limitation in the README. The other LLM10 controls (character limit, call cap, time budget, timeouts,
  budget alerts) are in place.

- The Bedrock steps in `docs/deployment.md` §8 stay pending until Bedrock access is unblocked.
  Until then the deployment runs with `LLM_ENABLED=false`, so the fail-safe masks every uncertain entity.

## Security tests

The suite has 394 tests passing on 27 Nov; run the security subset with `uv run pytest -m security`.
This review added: settings bounds (`tests/test_config.py`), token replay after logout
(`tests/test_auth.py`), and the deployed-image 401/200 check (`deploy.yml`).
Spoofed `X-Forwarded-For` is not an issue today: `client_id` uses `request.client.host`, not the
header. No test pins this behaviour yet.
