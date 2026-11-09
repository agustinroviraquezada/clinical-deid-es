"""AWS Lambda entry point: adapts Function URL events to the FastAPI app (design §9, §11)."""

from mangum import Mangum

from clinical_deid.api.app import app

# The lifespan protocol is not needed yet (no startup work), so it is turned off.
handler = Mangum(app, lifespan="off")
