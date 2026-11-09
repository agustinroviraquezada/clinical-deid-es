# `api/` — HTTP layer (FastAPI)

The outermost layer: receives HTTP requests, validates them with Pydantic and delegates to the
core. In production it runs on AWS Lambda behind a Function URL (design §9, ADR-0005); locally
it runs with uvicorn.

## Files

| File | Content | Status |
| --- | --- | --- |
| `app.py` | `FastAPI` instance and routes | T1.3: `GET /api/health` |
| `schemas.py` | Pydantic request/response models (DTOs) | T1.3: `HealthResponse` |
| `auth.py` | Demo login (FR-08) | T4.2 |
| `static/` | `index.html`, `app.js`, `styles.css` | T4.1 |

## Routes

| Method | Route | Auth | Status |
| --- | --- | --- | --- |
| GET | `/api/health` | No | Done — returns `{"status": "ok", "version": "<package version>"}`, no user data |
| POST | `/api/deidentify` | Yes | T2.6 |
| POST | `/api/login`, `/api/logout` | — | T4.2 |
| GET | `/api/comparison` | Yes | T3.4 / T4.1 |

Full contract: `specs/design.md` §6.

## Run locally

```bash
uv run uvicorn clinical_deid.api.app:app --reload --port 8000
curl http://localhost:8000/api/health
```

Interactive docs: <http://localhost:8000/docs>.

## Rules
- Never log request bodies or returned text (NFR-01, NFR-02): metadata only.
- Settings come from `config.py` (pydantic-settings), not `os.environ`.

Tests: `tests/test_api.py` (FastAPI `TestClient`, no server needed).
