"""Health-check response schema."""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Readiness and liveness state for the API."""

    status: str
    app: str
    version: str
