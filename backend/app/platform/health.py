"""Health check router: liveness and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.platform.db.session import check_database_connectivity
from app.platform.valkey.valkey_backend import check_valkey_connectivity

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    status: str = "alive"


class ReadinessResponse(BaseModel):
    status: str
    database: bool
    valkey: bool


@router.get("/health/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Process-alive check only. No dependency calls."""
    return LivenessResponse()


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(response: Response) -> ReadinessResponse:
    """Checks DB + Valkey connectivity. Returns 503 if either is unreachable."""
    db_ok = await check_database_connectivity()
    valkey_ok = await check_valkey_connectivity()
    ready = db_ok and valkey_ok

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if ready else "not_ready", database=db_ok, valkey=valkey_ok
    )
