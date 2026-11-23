"""FastAPI application."""

import logging
import time
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from clinical_deid import __version__
from clinical_deid.adapters.disabled_llm import DisabledVerifier
from clinical_deid.api.schemas import (
    DeidentifyRequest,
    DeidentifyResponse,
    EntityOut,
    HealthResponse,
    Metrics,
)
from clinical_deid.cascade import Cascade
from clinical_deid.config import get_settings

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

app = FastAPI(title="clinical-deid", version=__version__)


@app.exception_handler(RequestValidationError)
async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Generic 400: FastAPI's default 422 body copies the rejected input, i.e. user text."""
    return JSONResponse(status_code=400, content={"detail": "Invalid request"})


@lru_cache(maxsize=1)
def get_cascade() -> Cascade:
    """Build the model-only cascade once per process.

    Loading happens on the first request instead of at import time: Lambda limits the init
    phase to 10 s, and loading torch plus the model can take longer on a cold start.
    """
    from clinical_deid.adapters.hf_ner import HFEntityDetector

    settings = get_settings()
    detector = HFEntityDetector.from_pretrained(settings.model_path)
    # The LLM is off until T3.5: a zero cap masks every uncertain entity without calling it.
    return Cascade(
        detector, DisabledVerifier(), threshold=settings.confidence_threshold, max_llm_calls=0
    )


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
