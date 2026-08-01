"""Centralized configuration for GitPilot.

All configuration is loaded from environment variables (optionally via .env) and
validated by Pydantic Settings. Secrets are never logged or exposed to clients.
"""
from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


class CookiePolicy(StrEnum):
    LAX = "lax"
    STRICT = "strict"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    APP_NAME: str = "GitPilot"
    APP_ENV: Environment = Environment.LOCAL
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = Field(default=False)

    # --- Secrets ---
    # Minimum 32 random bytes. In production, set via a secret manager.
    SECRET_KEY: str = Field(min_length=32)
    # Key used for AES-256-GCM token vault. 32 bytes, hex-encoded.
    TOKEN_ENCRYPTION_KEY: str = Field(min_length=64)
    # Separate key that encrypts session payloads.
    SESSION_ENCRYPTION_KEY: str = Field(default="")

    # --- OAuth / GitHub App ---
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/oauth/github/callback"
    GITHUB_SCOPE: str = "read:user user:email"
    GITHUB_API_BASE_URL: str = "https://api.github.com"
    GITHUB_WEB_BASE_URL: str = "https://github.com"
    GITHUB_APP_TYPE: Literal["oauth_app", "github_app"] = "oauth_app"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://gitpilot:gitpilot@localhost:5432/gitpilot"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 40
    DB_ECHO: bool = False

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_SESSION_DB: int = 1

    # --- Sessions ---
    SESSION_TTL_SECONDS: int = 60 * 60 * 8  # 8h absolute, rotated periodically
    SESSION_IDLE_TIMEOUT_SECONDS: int = 60 * 30  # 30m idle
    SESSION_ROTATION_SECONDS: int = 60 * 15  # rotate id every 15m
    SESSION_COOKIE_NAME: str = "gp_session"
    SESSION_COOKIE_SAMESITE: CookiePolicy = CookiePolicy.LAX
    SESSION_COOKIE_DOMAIN: str = ""

    # --- OAuth state / PKCE ---
    OAUTH_STATE_TTL_SECONDS: int = 600  # 10 minutes
    PKCE_TTL_SECONDS: int = 600
    OAUTH_VERIFIER_LENGTH: int = 64

    # --- Rate limiting ---
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 10
    RATE_LIMIT_GLOBAL_PER_MINUTE: int = 600
    RATE_LIMIT_AUTH_PER_MINUTE: int = 30

    # --- GitHub API client ---
    GH_RETRY_MAX_ATTEMPTS: int = 5
    GH_RETRY_BASE_BACKOFF: float = 0.5
    GH_HTTP_TIMEOUT_SECONDS: float = 30.0
    GH_MAX_RETRY_WAIT_SECONDS: float = 8.0
    GH_CACHE_TTL_SECONDS: int = 60

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- Security ---
    ARGON2_TIME_COST: int = 3
    ARGON2_MEMORY_COST: int = 65536
    ARGON2_PARALLELISM: int = 2
    EMAIL_VERIFICATION_TOKEN_TTL: int = 60 * 60
    HSTS_MAX_AGE: int = 31536000
    TRUST_PROXY_HEADERS: bool = False

    @field_validator("GITHUB_SCOPE")
    @classmethod
    def _normalize_scopes(cls, v: str) -> str:
        return " ".join(dict.fromkeys(v.split()))

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        if self.APP_ENV != Environment.TESTING and not self.GITHUB_CLIENT_ID:
            raise ValueError("GITHUB_CLIENT_ID must be configured for non-testing environments")
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.APP_ENV == Environment.TESTING

    @property
    def cookie_secure(self) -> bool:
        return self.APP_ENV in {Environment.STAGING, Environment.PRODUCTION}


@lru_cache
def get_settings() -> Settings:
    return Settings()
