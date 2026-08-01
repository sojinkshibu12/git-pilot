# Deployment

## Prerequisites
- Docker Engine + Docker Compose v2 (production: orchestrator with PostgreSQL
  16 + Redis 7 + TLS-terminating reverse proxy).
- DNS pointing at the host; TLS certs (Let's Encrypt via certbot or K8s cert-manager).
- A GitHub **OAuth App** (or GitHub App) with:
  - Homepage URL: `https://gitpilot.example.com`
  - Authorization callback URL: `https://gitpilot.example.com/api/v1/oauth/github/callback`

## Environment
Copy `backend/.env.example` to `backend/.env` and `frontend/.env.example` to
`frontend/.env`. Every variable is validated at startup by
`backend/app/core/config.py`. See `environment.md` for the full reference.

## Production quick start (Docker Compose)

```bash
cp backend/.env.example backend/.env
# edit backend/.env: SECRET_KEY, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET,
#                   DATABASE_URL, REDIS_URL, FRONTEND_PUBLIC_BASE_URL
cp frontend/.env.example frontend/.env
export GITPILOT_ENV=production
docker compose --profile full up -d --build
docker compose exec migrate alembic upgrade head   # or the migrate service
```

Profiles:
- `migrate` — run migrations then exit.
- `backend` — FastAPI (uvicorn, `--workers N` behind Nginx).
- `frontend` — Next.js standalone build served by Nginx.
- `nginx` — TLS termination, static assets, proxy `/api/v1/*`.
- `full` — everything except local Postgres/Redis when using external services.

## Nginx
`infra/nginx/nginx.conf`:
- TLS 1.2/1.3, HSTS, secure cipher list, OCSP stapling.
- `X-Frame-Options: DENY`, `X-Content-Type-Options`, CSP.
- `location /api/` → upstream `backend:8000`.
- Static + gzip for the Next.js export/standalone output.
- Rate limiting (`limit_req`) at the edge for auth endpoints.

## CI/CD
`.github/workflows/ci.yml`: lint (ruff, prettier/eslint), unit + integration
tests (Postgres+Redis services), Alembic upgrade from clean DB, coverage gate
(≥90%), Playwright smoke against a build of the stack.
`.github/workflows/cd.yml`: build + push images to GHCR, deploy via SSH/Helm.

## Database migration
```bash
docker compose run --rm migrate alembic revision --autogenerate -m "change"
docker compose run --rm migrate alembic upgrade head
```
Never hand-edit applied migrations; add a new revision.

## Scaling
- API: run ≥2 replicas; sessions/cache/rate-limits in Redis → zero sticky state.
- Postgres: connection pooling (pgbouncer) optional; enable `max_connections`.
- Redis: HA with Sentinel/Cluster for production.
- Health checks: `/health` (liveness) and `/health/ready` (DB+Redis probes);
  Nginx or orchestrator routes on readiness.

## Backup & recovery
- Postgres: `pg_dump` nightly + WAL archiving; restore drills.
- Redis is **cache-only** for sessions (Postgres also holds session rows), so
  Redis loss forces re-login, never data loss.
- `SECRET_KEY` loss = unrecoverable token vault. Store in a KMS/secret manager.

## Monitoring & alerting
- Structured JSON logs (stdout) → Loki/Datadog; `request_id`/`correlation_id`.
- Metrics: /health, request latency, GitHub rate-limit headroom, 401/429 rates,
  audit error rate, failed-login spikes.
- Alert on: repeated OAuth `state` mismatches (CSRF/probe), lockouts, audit
  failures, GitHub API rate-limit exhaustion.

## Rollback
- Backend: previous Docker image + Alembic downgrade script.
- Never downgrade past a credential encryption version bump without a data fix.
