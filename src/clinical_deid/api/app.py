"""FastAPI application."""

from fastapi import FastAPI

from clinical_deid import __version__
from clinical_deid.api.schemas import HealthResponse

app = FastAPI(title="clinical-deid", version=__version__)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness check."""
    return HealthResponse(status="ok", version=__version__)
