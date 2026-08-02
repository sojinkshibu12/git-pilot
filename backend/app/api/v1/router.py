from fastapi import APIRouter

from app.api.v1.endpoints import (
    api_keys,
    audit,
    auth,
    contributions,
    health,
    issues,
    oauth,
    repositories,
    sessions,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(oauth.router)
api_router.include_router(sessions.router)
api_router.include_router(users.router)
api_router.include_router(repositories.router)
api_router.include_router(issues.router)
api_router.include_router(contributions.router)
api_router.include_router(api_keys.router)
api_router.include_router(audit.router)
api_router.include_router(health.router)
