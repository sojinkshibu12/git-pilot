"""Pydantic v2 request/response schemas.

These define the wire contract of the API and never leak tokens or secrets.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.domain.models.enums import AuthProvider, SessionStatus


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
class RegisterRequest(BaseModel):
    email: EmailStr = Field(min_length=5, max_length=320)
    password: str = Field(min_length=12, max_length=128)
    display_name: str | None = Field(default=None, max_length=160)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        checks = {
            "at least 12 characters": len(v) >= 12,
            "an uppercase letter": any(c.isupper() for c in v),
            "a lowercase letter": any(c.islower() for c in v),
            "a digit": any(c.isdigit() for c in v),
        }
        failed = [label for label, ok in checks.items() if not ok]
        if failed:
            raise ValueError(f"Password must include {', '.join(failed)}")
        return v


class LoginRequest(BaseModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("Password must be at least 12 characters")
        return v


class EmailVerificationRequest(BaseModel):
    token: str = Field(min_length=20)


class AccountLinkRequest(BaseModel):
    provider: Literal["github"]
    state: str = Field(min_length=16)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


# --------------------------------------------------------------------------- #
# OAuth
# --------------------------------------------------------------------------- #
class OAuthAuthorizeResponse(BaseModel):
    authorize_url: str
    state: str
    pkce_method: str = "S256"


class OAuthUserResponse(BaseModel):
    id: uuid.UUID
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None
    avatar_url: str | None = None
    github: "GitHubAccountSchema | None" = None


class GitHubAccountSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    github_id: int
    login: str
    display_name: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    email_verified: bool = False
    html_url: str | None = None
    github_type: str = "User"
    plan: str | None = None
    organizations: list[str] = Field(default_factory=list)


class AccountLinkStatusResponse(BaseModel):
    needs_linking: bool = False
    link_provider: AuthProvider | None = None
    link_state: str | None = None
    candidate_email: str | None = None


# --------------------------------------------------------------------------- #
# Sessions
# --------------------------------------------------------------------------- #
class SessionInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    device_label: str | None = None
    is_current: bool = False
    status: SessionStatus


class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]


class LogoutAllResponse(BaseModel):
    revoked: int


class SessionExpiredInfo(BaseModel):
    detail: str
    code: str
    expires_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------------- #
class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None
    avatar_url: str | None = None
    locale: str = "en"
    plan: str = "free"
    mfa_enabled: bool = False
    created_at: datetime


class UpdateProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=160)
    locale: str | None = Field(default=None, max_length=16)
    avatar_url: str | None = Field(default=None, max_length=1024)


class UserPreferencesSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    theme: str = "system"
    email_notifications: bool = True
    default_repo_visibility: str = "private"
    timezone: str | None = None


class UpdatePreferencesRequest(BaseModel):
    theme: Literal["light", "dark", "system"] = "system"
    email_notifications: bool = True
    default_repo_visibility: Literal["public", "private", "internal"] = "private"
    timezone: str | None = Field(default=None, max_length=64)


# --------------------------------------------------------------------------- #
# Security / connected accounts
# --------------------------------------------------------------------------- #
class ConnectedAccount(BaseModel):
    provider: AuthProvider
    display_name: str | None = None
    connected: bool = False
    primary: bool = False
    github_id: int | None = None
    login: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    email_verified: bool = False


class SecurityOverview(BaseModel):
    has_password: bool
    mfa_enabled: bool
    email_verified: bool
    connected_accounts: list[ConnectedAccount]
    active_sessions_count: int


class APIKeySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str] = Field(default_factory=list)
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime


class APIKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list)


class APIKeyCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    key: str  # shown once


class GenericSuccess(BaseModel):
    detail: str = "success"
    data: dict[str, Any] | None = None


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class ErrorDetail(BaseModel):
    detail: str
    code: str = "error"
    status: int = 400
    fields: dict[str, list[str]] | None = None
    retry_after_seconds: int | None = None


class ValidationErrorResponse(BaseModel):
    detail: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    database: bool
    redis: bool
    uptime_seconds: float


OAuthUserResponse.model_rebuild()
