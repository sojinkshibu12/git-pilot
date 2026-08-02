"""Issue endpoints — issues assigned to the authenticated user across repos.

GitHub's `/issues` endpoint with `filter=assigned` returns every issue assigned
to the current user (including "good first issue" / "help wanted" picks made by
maintainers), which powers the sidebar's "Assigned issues" page.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import AuthenticatedContext, get_authenticated_context
from app.application.dependencies import Services, get_services

router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("/assigned", summary="Issues assigned to the current user")
async def list_assigned_issues(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    state: str = Query("open", pattern="^(open|closed|all)$"),
) -> dict[str, Any]:
    return {"issues": await services.repos.list_assigned_issues(context.user.id, state=state)}
