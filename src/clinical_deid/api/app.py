"""FastAPI application."""

import json
import logging
import time
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from clinical_deid import __version__
from clinical_deid.adapters.disabled_llm import DisabledVerifier
from clinical_deid.api.auth import (
    COOKIE_NAME,
    SESSION_TTL_S,
    client_id,
    login_attempts,
    new_session_token,
    require_session,
    verify_credentials,
)
from clinical_deid.api.schemas import (
    DeidentifyRequest,
    DeidentifyResponse,
    EntityOut,
    HealthResponse,
    LoginRequest,
    Metrics,
)
from clinical_deid.cascade import Cascade
from clinical_deid.config import get_settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

API_DIR = Path(__file__).resolve().parent
STATIC_DIR = API_DIR / "static"
REPORT_DIR = API_DIR / "report"

app = FastAPI(title="clinical-deid", version=__version__)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Generic 400: FastAPI's default 422 body copies the rejected input, i.e. user text."""
    return JSONResponse(status_code=400, content={"detail": "Invalid request"})


@lru_cache(maxsize=1)
def get_cascade() -> Cascade:
    """Build the cascade once per process.

    Loading happens on the first request instead of at import time: Lambda limits the init
    phase to 10 s, and loading torch plus the model can take longer on a cold start.
    """
    from clinical_deid.adapters.hf_ner import HFEntityDetector

    settings = get_settings()
    detector = HFEntityDetector.from_pretrained(settings.model_path)
    if not settings.llm_enabled:
        # Model only: a zero cap masks every uncertain entity without calling an LLM.
        return Cascade(
            detector, DisabledVerifier(), threshold=settings.confidence_threshold, max_llm_calls=0
        )

    from clinical_deid.adapters.bedrock_llm import BedrockVerifier

    return Cascade(
        detector,
        BedrockVerifier.from_settings(),
        threshold=settings.confidence_threshold,
        max_llm_calls=settings.max_llm_sentences,
        llm_time_budget_s=settings.llm_time_budget_s,
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Single-page web interface (T4.1)."""
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.post("/api/login")
def login(credentials: LoginRequest, request: Request, response: Response) -> dict:
    """Demo login (FR-08): signed session cookie, attempt limit, generic errors."""
    client = client_id(request)
    if login_attempts.is_locked(client):
        logger.warning("login locked out")
        raise HTTPException(status_code=429, detail="Too many attempts. Try again later")
    if not verify_credentials(credentials.username, credentials.password):
        login_attempts.record_failure(client)
        # Metadata only: never the username or the password.
        logger.info("login failed")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    login_attempts.clear(client)
    response.set_cookie(
        COOKIE_NAME,
        new_session_token(),
        max_age=SESSION_TTL_S,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/",
    )
    logger.info("login ok")
    return {"status": "ok"}


@app.post("/api/logout", dependencies=[Depends(require_session)])
def logout(response: Response) -> dict:
    """End the session by expiring the cookie in the browser."""
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=True, samesite="strict")
    return {"status": "ok"}


@lru_cache(maxsize=1)
def _comparison_report() -> dict:
    return json.loads((REPORT_DIR / "comparison.json").read_text(encoding="utf-8"))


@app.get("/api/comparison", dependencies=[Depends(require_session)])
def comparison() -> dict:
    """Precomputed results of the three configurations (FR-11)."""
    return _comparison_report()


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse(status="ok", version=__version__)


def within_size_limit(request: DeidentifyRequest) -> DeidentifyRequest:
    """413 over MAX_CHARACTERS (FR-01, LLM10).

    Declared before the cascade dependency, so an oversized request is rejected before the
    model is loaded and never pays for a cold start.
    """
    max_characters = get_settings().max_characters
    if len(request.text) > max_characters:
        raise HTTPException(
            status_code=413, detail=f"Text is longer than {max_characters} characters"
        )
    return request


@app.post("/api/deidentify", response_model=DeidentifyResponse)
def deidentify(
    _session: Annotated[None, Depends(require_session)],
    request: Annotated[DeidentifyRequest, Depends(within_size_limit)],
    cascade: Annotated[Cascade, Depends(get_cascade)],
) -> DeidentifyResponse:
    """Mask the personal data of one note (FR-01, FR-03)."""
    started = time.perf_counter()
    result = cascade.run(request.text)
    latency_ms = round((time.perf_counter() - started) * 1000)

    # Metadata only (NFR-01, NFR-02): never the text or the entities' values.
    logger.info(
        "deidentify chars=%d entities=%d n_llm=%d latency_ms=%d",
        len(request.text),
        len(result.entities),
        result.n_llm,
        latency_ms,
    )
    return DeidentifyResponse(
        deidentified_text=result.deidentified_text,
        entities=[
            EntityOut(
                start=e.start,
                end=e.end,
                category=e.category,
                source="llm" if (e.start, e.end) in result.llm_verified else "model",
            )
            for e in result.entities
        ],
        metrics=Metrics(latency_ms=latency_ms, n_entities=len(result.entities), n_llm=result.n_llm),
    )
