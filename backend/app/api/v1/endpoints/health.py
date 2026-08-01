"""Health + readiness endpoints."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Request

from app.schemas import HealthResponse

router = APIRouter(tags=["system"])

_STARTED = time.time()


@router.get("/health", response_model=HealthResponse, summary="Liveness + dependency health")
async def health(request: Request) -> HealthResponse:
    db_ok = bool(getattr(request.app.state, "db", None))
    redis = getattr(request.app.state, "redis", None)
    redis_ok = await redis.ping() if redis else False
    return HealthResponse(
        status="ok" if db_ok and redis_ok else "degraded",
        version=getattr(request.app.state, "version", "unknown"),
        database=db_ok,
        redis=redis_ok,
        uptime_seconds=round(time.time() - _STARTED, 2),
    )


@router.get("/ready", summary="Readiness (migrations applied, deps reachable)")
async def ready(request: Request) -> dict[str, Any]:
    redis = getattr(request.app.state, "redis", None)
    redis_ok = await redis.ping() if redis else False
    return {"ready": redis_ok, "redis": redis_ok}
