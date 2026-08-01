"""Dependency injection for the application layer.

Services are constructed per-request, sharing the request-scoped DB session and
the shared infrastructure singletons on `request.app.state`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.audit_service import AuditService
from app.application.services.auth_service import AuthService
from app.application.services.contribution_service import ContributionService
from app.application.services.oauth_service import OAuthService
from app.application.services.repository_service import RepositoryService
from app.application.services.session_service import SessionService
from app.application.services.token_service import TokenService
from app.application.services.user_service import UserService
from app.core.config import Settings, get_settings
from app.core.security import TokenVault
from app.infrastructure.db.session import get_db_session
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.redis.client import RedisClient
from app.infrastructure.security.rate_limiter import RateLimiter


@dataclass
class Services:
    db: AsyncSession
    redis: RedisClient
    vault: TokenVault
    github: GitHubAPIClient
    settings: Settings
    audit: AuditService
    sessions: SessionService
    tokens: TokenService
    auth: AuthService
    oauth: OAuthService
    users: UserService
    repos: RepositoryService
    contributions: ContributionService
    rate_limiter: RateLimiter


async def get_services(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Services:
    """Build the service graph for the current request."""
    app = request.app
    redis: RedisClient = app.state.redis
    vault: TokenVault = app.state.vault
    github: GitHubAPIClient = app.state.github
    settings: Settings = get_settings()

    audit = AuditService(session)
    sessions = SessionService(session, redis, settings, audit)
    tokens = TokenService(session, vault)
    oauth = OAuthService(
        settings=settings, db=session, vault=vault, audit=audit, github=github, redis=redis
    )
    auth = AuthService(
        settings=settings, db=session, redis=redis, audit=audit, sessions=sessions, oauth=oauth, tokens=tokens
    )
    users = UserService(db=session, audit=audit, sessions=sessions, tokens=tokens, github=github)
    repos = RepositoryService(github=github, tokens=tokens, audit=audit)
    contributions = ContributionService(db=session, github=github, tokens=tokens, audit=audit, redis=redis)
    rate_limiter = RateLimiter(redis)

    return Services(
        db=session,
        redis=redis,
        vault=vault,
        github=github,
        settings=settings,
        audit=audit,
        sessions=sessions,
        tokens=tokens,
        auth=auth,
        oauth=oauth,
        users=users,
        repos=repos,
        contributions=contributions,
        rate_limiter=rate_limiter,
    )


ServicesDep = Annotated[Services, Depends(get_services)]
