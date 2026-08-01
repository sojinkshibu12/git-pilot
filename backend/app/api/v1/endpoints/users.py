"""User profile, preferences, and connected-accounts endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import CsrfGuard, CurrentUser, get_authenticated_context
from app.application.dependencies import Services, get_services
from app.schemas import (
    GenericSuccess,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
    UserPreferencesSchema,
    UserProfile,
)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile, summary="Get current user profile")
async def get_profile(
    current_user: CurrentUser,
    services: Annotated[Services, Depends(get_services)],
) -> UserProfile:
    return UserProfile.model_validate(current_user)


@router.patch("/me", response_model=UserProfile, summary="Update profile")
async def update_profile(
    payload: UpdateProfileRequest,
    context=Depends(get_authenticated_context),
    _csrf: CsrfGuard = None,
    services: Annotated[Services, Depends(get_services)] = None,
) -> UserProfile:
    user = await services.users.update_profile(
        context.user.id,
        **payload.model_dump(exclude_none=True),
    )
    await services.db.commit()
    return UserProfile.model_validate(user)


@router.get("/me/preferences", response_model=UserPreferencesSchema, summary="Get preferences")
async def get_preferences(
    context=Depends(get_authenticated_context),
    services: Annotated[Services, Depends(get_services)] = None,
) -> UserPreferencesSchema:
    prefs = await services.users.get_preferences(context.user.id)
    await services.db.commit()
    return UserPreferencesSchema.model_validate(prefs)


@router.patch("/me/preferences", response_model=UserPreferencesSchema, summary="Update preferences")
async def update_preferences(
    payload: UpdatePreferencesRequest,
    context=Depends(get_authenticated_context),
    _csrf: CsrfGuard = None,
    services: Annotated[Services, Depends(get_services)] = None,
) -> UserPreferencesSchema:
    prefs = await services.users.update_preferences(
        context.user.id, **payload.model_dump(exclude_none=True)
    )
    await services.db.commit()
    return UserPreferencesSchema.model_validate(prefs)


@router.get("/me/connected-accounts", summary="List connected identity providers")
async def connected_accounts(
    context=Depends(get_authenticated_context),
    services: Annotated[Services, Depends(get_services)] = None,
):
    return {"accounts": await services.users.list_connected_accounts(context.user.id)}


@router.get("/me/security", summary="Security overview (password, MFA, accounts, sessions)")
async def security_overview(
    context=Depends(get_authenticated_context),
    services: Annotated[Services, Depends(get_services)] = None,
):
    return await services.users.security_overview(context.user.id)


@router.post(
    "/me/unlink/github/{github_account_id}",
    response_model=GenericSuccess,
    summary="Unlink a GitHub account",
)
async def unlink_github(
    github_account_id: str,
    context=Depends(get_authenticated_context),
    _csrf: CsrfGuard = None,
    services: Annotated[Services, Depends(get_services)] = None,
) -> GenericSuccess:
    import uuid

    await services.auth.unlink_github(user_id=context.user.id, github_account_id=uuid.UUID(github_account_id))
    await services.db.commit()
    return GenericSuccess(detail="GitHub account unlinked.")
