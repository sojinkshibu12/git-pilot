# GitPilot — Enterprise GitHub Authentication & Authorization Platform

GitPilot is a production-grade, enterprise SaaS platform that authenticates users with
GitHub and exposes a secure gateway to the GitHub REST + GraphQL APIs. It is architected
to scale to thousands of organizations and millions of repositories.

> **Security-first.** OAuth 2.1 Authorization Code Flow + PKCE, cryptographically-bound
> `state`, server-side encrypted token storage (AES-256-GCM), HttpOnly/Secure/SameSite
> session cookies, full audit logging, and OWASP ASVS-aligned controls throughout.

---

## Repository Layout

```
git-pilot/
├── backend/            # FastAPI + SQLAlchemy 2 + Alembic + Redis
│   ├── app/
│   │   ├── api/        # REST API layer (FastAPI routes, DTOs)
│   │   ├── application/# Use-cases / services (business logic)
│   │   ├── core/       # Config, logging, exceptions, security primitives
│   │   ├── domain/     # Entities, value objects, enums (framework-free)
│   │   ├── infrastructure/ # DB, Redis, GitHub client, token vault
│   │   └── schemas/    # Pydantic v2 request/response models
│   ├── alembic/        # DB migrations
│   └── tests/          # unit / integration / security / e2e
├── frontend/           # Next.js 15 App Router + React 19 + Tailwind
├── infra/              # Docker, Nginx, CI/CD
└── docs/               # Architecture, threat model, deployment, Postman
```

## Quickstart (Docker)

```bash
cp infra/docker/.env.example .env
docker compose --profile full up --build
# Frontend   → http://localhost:3000
# API        → http://localhost:8000/docs
# Postgres   → localhost:5432   Redis → localhost:6379
```

## Documentation

| Doc | Path |
|---|---|
| Architecture | `docs/architecture.md` |
| OAuth sequence | `docs/oauth-sequence.md` |
| Database ER | `docs/database.md` |
| Security guide | `docs/security.md` |
| Threat model | `docs/threat-model.md` |
| Deployment | `docs/deployment.md` |
| API / OpenAPI | `docs/api.md` · `/docs` (Swagger) |
| Postman collection | `docs/postman/` |

## Environment

See `backend/.env.example`, `frontend/.env.example`, and `docs/environment.md`.

## License

Proprietary.
