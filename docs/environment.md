# Environment reference

All configuration is **env-driven** and validated by Pydantic Settings in
`backend/app/core/config.py`. Startup fails fast on missing/invalid values.

## Backend variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `APP_NAME` | – | `GitPilot` | display name |
| `APP_ENV` | – | `local` | `local\|testing\|staging\|production` |
| `APP_VERSION` | – | `1.0.0` | build version |
| `DEBUG` | – | `false` | dev-only; forces no-op security in local |
| `SECRET_KEY` | **prod** | – | ≥32 bytes; **production refuses the dev default** |
| `TOKEN_ENCRYPTION_KEY` | **prod** | – | 64 hex chars (32 bytes) → AES-256-GCM vault. **Loss = data unrecoverable.** |
| `SESSION_ENCRYPTION_KEY` | – | – | optional, if session payloads are encrypted |
| `GITHUB_CLIENT_ID` | **yes** | – | GitHub OAuth App client id |
| `GITHUB_CLIENT_SECRET` | **yes** | – | GitHub OAuth App secret (backend only) |
| `GITHUB_REDIRECT_URI` | **yes** | – | exact registered redirect URI |
| `GITHUB_SCOPE` | – | `read:user user:email` | requested scopes |
| `GITHUB_API_BASE_URL` | – | `https://api.github.com` | proxy base |
| `GITHUB_WEB_BASE_URL` | – | `https://github.com` | authorize base |
| `GITHUB_APP_TYPE` | – | `oauth_app` | `oauth_app\|github_app` (github_app is the future upgrade) |
| `DATABASE_URL` | **yes** | – | `postgresql+asyncpg://…` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | – | 20 / 40 | SQLAlchemy pool |
| `DB_ECHO` | – | `false` | SQL echo (dev) |
| `REDIS_URL` | **yes** | – | `redis://…` (sessions, cache, rate-limit) |
| `SESSION_TTL_SECONDS` | – | 28800 (8h) | absolute session lifetime |
| `SESSION_IDLE_TIMEOUT_SECONDS` | – | 1800 (30m) | sliding idle timeout |
| `SESSION_ROTATION_SECONDS` | – | 900 (15m) | rotate token after this interval |
| `SESSION_COOKIE_NAME` | – | `gp_session` | cookie name |
| `SESSION_COOKIE_SAMESITE` | – | `lax` | cookie SameSite |
| `CORS_ORIGINS` | – | `["http://localhost:3000"]` | allowed browser origins |

## Frontend variables
| Variable | Description |
|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | `https://<host>/api/v1` (browser-visible) |

## Secrets policy
- Generate strong secrets:
  ```bash
  openssl rand -hex 32   # SECRET_KEY and TOKEN_ENCRYPTION_KEY
  ```
- Rotate `TOKEN_ENCRYPTION_KEY` via re-encryption job (token re-encryption
  script) — never change it casually; it invalidates all stored tokens.
- Store in a KMS/secret manager in production; never in git, image layers, or
  client bundles.
- `DEBUG=true` and the default `SECRET_KEY` cause a **refusal to boot** when
  `APP_ENV=production`.

## GitHub OAuth App setup
1. GitHub → Settings → Developer settings → OAuth Apps → New.
2. Authorization callback URL: exactly `GITHUB_REDIRECT_URI`.
3. Homepage URL: your frontend origin.
4. Scopes: `read:user user:email` (extend per feature: `repo`, `workflow`, …).
5. Put id/secret in `backend/.env`; restart backend.
