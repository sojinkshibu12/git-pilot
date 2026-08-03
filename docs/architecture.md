# Architecture

GitPilot is a horizontally-scalable, security-first platform that authenticates users with GitHub (OAuth 2.1 + PKCE) and provides a secure gateway to the GitHub REST + GraphQL APIs.

## System diagram

```
                         ┌─────────────────────────────────────────────────────┐
                         │                     Browser (Next.js)              │
                         │   Auth UI · Dashboard · Security Center           │
                         └───────────────┬───────────────────────┬────────────┘
                                         │ HttpOnly session       │ API calls
                                         │ cookie                 │ (X-CSRF-Token)
                                         ▼                       ▼
┌────────────┐              ┌──────────────────────┐   ┌──────────────────────┐
│   GitHub   │◄────────────►│       Nginx          │   │  Next.js (3000)      │
│  OAuth App │  authorize/  │  TLS · WAF · static  │   └──────────────────────┘
│  REST API  │  token/API   └──────────┬───────────┘
│  GraphQL   │                         │ /api/v1/*
└────────────┘                         ▼
                        ┌─────────────────────────────────────────┐
                        │            FastAPI (8000)               │
                        │  api → application → domain → infra     │
                        │                                         │
                        │  OAuth flow · sessions · token vault    │
                        │  GitHub client · audit · rate limiting  │
                        └───────┬──────────────┬─────────┬────────┘
                                │              │         │
                    ┌───────────▼──┐   ┌───────▼─────┐  ┌▼──────────────────┐
                    │  PostgreSQL  │   │   Redis     │  │  TokenVault       │
                    │  (durable,   │   │  sessions   │  │  AES-256-GCM      │
                    │  audit,      │   │  cache,     │  │  (SECRET in env)  │
                    │  entities)   │   │  rate limit │  └───────────────────┘
                    └──────────────┘   └─────────────┘
```

## Layered architecture (Clean Architecture / DDD)

```
┌────────────────────────────────────────────────────────────┐
│ UI  (frontend/)                                            │
│   Next.js 15 App Router · React 19 · Tailwind · Framer     │
├────────────────────────────────────────────────────────────┤
│ API (backend/app/api/)                                     │
│   Routers · DTOs (Pydantic v2) · deps · middleware ·       │
│   error handlers · cookies · CSRF                          │
├────────────────────────────────────────────────────────────┤
│ Application (backend/app/application/services/)            │
│   AuthService · OAuthService · SessionService ·            │
│   TokenService · UserService · RepositoryService ·         │
│   AuditService                                             │
├────────────────────────────────────────────────────────────┤
│ Domain (backend/app/domain/)                               │
│   Entities (User, GitHubAccount, Session, ...)             │
│   Enums · invariants · identifiers (UUID)                  │
├────────────────────────────────────────────────────────────┤
│ Infrastructure (backend/app/infrastructure/)               │
│   db/ (SQLAlchemy 2 + Alembic) · redis/ · github/          │
│   security/ (vault, session store, rate limiter)           │
├────────────────────────────────────────────────────────────┤
│ Core (backend/app/core/)                                   │
│   config (Pydantic Settings) · logging (structlog) ·       │
│   exceptions · security primitives (PKCE, AES-GCM, Argon2) │
└────────────────────────────────────────────────────────────┘
```

**Dependency rule:** higher layers depend on lower layers only. Domain has zero
framework imports. Infrastructure implements repository interfaces consumed by
application services via constructor injection (see `app/application/dependencies.py`).

## Key flows

| Flow | Where |
|---|---|
| Email/password registration + login | `AuthService`, `app/api/v1/endpoints/auth.py` |
| GitHub OAuth (code + PKCE + state) | `OAuthService`, `app/api/v1/endpoints/oauth.py` |
| Account linking (GitHub↔Password) | `OAuthService.complete_link`, link UI |
| Session lifecycle (create/rotate/revoke) | `SessionService` + Redis `SessionStore` |
| Token encryption + storage | `TokenService` + `TokenVault` (AES-256-GCM) |
| GitHub REST/GraphQL gateway | `GitHubAPIClient` + `RepositoryService` |
| Audit trail | `AuditService` (DB row + SIEM-ready structured logs) |

## Scalability & operations

- **Horizontal scaling:** stateless API replicas share Redis (sessions, cache,
  rate limits) and PostgreSQL. No local sticky state.
- **GitHub Apps (server-to-server):** the GitHub client abstracts auth via a
  bearer token. Setting `GITHUB_APP_TYPE=github_app` enables
  `GitHubAppAuthService`, which signs an RS256 app JWT, resolves the app
  installation per owner/repo, and issues cached installation access tokens.
  Repo-scoped calls (issues, PRs, contents, comments) then run with the app's
  read/write permissions via `RepositoryService._repo_token_for`, while
  user-scoped reads (assigned issues, profile/contributions) keep the signed-in
  user's OAuth token. Controllers are unchanged.
- **Observability:** structured JSON logs with `request_id`/`correlation_id`,
  health/readiness endpoints, and audit stream.
- **Cache:** ETag conditional requests + TTL cache in Redis; rate-limit counters.
