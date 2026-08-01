"""Contribution heatmap endpoints.

Serve the GitHub-style contribution grid (with per-type breakdowns), streak and
statistics. Data is aggregated once from GitHub and cached per user + year.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import AuthenticatedContext, CsrfGuard, get_authenticated_context
from app.application.dependencies import Services, get_services
from app.core.exceptions import ValidationFailure
from app.schemas import GenericSuccess

router = APIRouter(prefix="/contributions", tags=["contributions"])

_MIN_YEAR = 2008


def _year(value: int) -> int:
    current = date.today().year
    if value < _MIN_YEAR or value > current:
        raise ValidationFailure(
            f"year must be between {_MIN_YEAR} and {current}.",
            year=value,
        )
    return value


@router.get("/", summary="Contribution heatmap for a year")
async def get_contributions(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    year: int = Query(default_factory=lambda: date.today().year),
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    return await services.contributions.get_year(context.user.id, _year(year), refresh=refresh)


@router.get("/streak", summary="Current + longest contribution streaks")
async def get_streaks(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    year: int = Query(default_factory=lambda: date.today().year),
) -> dict[str, Any]:
    return await services.contributions.get_streaks(context.user.id, _year(year))


@router.get("/statistics", summary="Contribution statistics for a year")
async def get_statistics(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    year: int = Query(default_factory=lambda: date.today().year),
) -> dict[str, Any]:
    return await services.contributions.get_statistics(context.user.id, _year(year))


@router.get("/{year}", summary="Contribution heatmap for a year (path form)")
async def get_contributions_by_year(
    year: int,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    return await services.contributions.get_year(context.user.id, _year(year), refresh=refresh)


@router.post("/refresh", response_model=GenericSuccess, summary="Re-aggregate a year from GitHub")
async def refresh_contributions(
    payload: dict[str, Any],
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    year = _year(int(payload.get("year", date.today().year)))
    ok = await services.contributions.refresh(context.user.id, year)
    await services.db.commit()
    return GenericSuccess(
        detail="Contributions refreshed." if ok else "No GitHub account linked.",
        data={"year": year, "connected": ok},
    )
