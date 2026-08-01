# API reference

Base URL: `https://<host>/api/v1` (dev: `http://localhost:8000/api/v1`).
All responses JSON; errors use the `ProblemDetail` envelope (RFC 7807-ish):

```json
{ "error": { "code": "not_found", "message": "…", "details": {}, "request_id": "…" } }
```

Interactive docs: `/docs` (Swagger UI) and `/redoc` (dev only).

## Authentication headers

| Scheme | How |
|---|---|
| Session | `Cookie: gp_session=…` (HttpOnly) |
| CSRF (mutations) | `X-CSRF-Token: <token from GET /sessions/csrf>` |
| API key | `Authorization: Bearer gp_…` |

## Health

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness + DB/Redis status |
| GET | `/ready` | readiness (migrations, deps) |

## Auth

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register` | – | `{email, password, name?}`; 201, sets session |
| POST | `/auth/login` | – | `{email, password}`; 200 sets session |
| POST | `/auth/logout` | session | revoke current |
| POST | `/auth/logout-all` | session | revoke all devices |
| GET | `/auth/me` | session | current profile |
| POST | `/auth/password/change` | session+CSRF | `{current_password, new_password}` |
| POST | `/auth/email/verify` | session+CSRF | `{token}` |
| POST | `/auth/email/resend` | session+CSRF | resend verification email |
| POST | `/auth/link/github` | session+CSRF | begin linking a GitHub identity |

## OAuth

| Method | Path | Notes |
|---|---|---|
| GET | `/oauth/github/begin` | 303 → GitHub authorize URL (state+PKCE issued) |
| GET | `/oauth/github/callback` | GitHub redirects here; 303 → frontend, or 409 `account_linking_required` with `link_token` |
| POST | `/oauth/link/complete` | `{link_token, email, password}` prove ownership & link |

## Sessions

| Method | Path | Notes |
|---|---|---|
| GET | `/sessions` | list active sessions |
| POST | `/sessions/{session_id}/revoke` | revoke one |
| POST | `/sessions/revoke-all` | revoke others |
| POST | `/sessions/csrf` | **returns the CSRF token** to attach via `X-CSRF-Token` |

## Users

| Method | Path | Notes |
|---|---|---|
| GET | `/users/me` | profile |
| PATCH | `/users/me` | `{name?, locale?, bio?}` |
| GET/PATCH | `/users/me/preferences` | notifications, theme, language |
| GET | `/users/me/connected-accounts` | linked identity providers |
| GET | `/users/me/security` | password state, MFA, accounts, sessions summary |

## API keys

| Method | Path | Notes |
|---|---|---|
| GET | `/api-keys` | list (no secrets) |
| POST | `/api-keys` | create; `key` returned once (`gp_…`) |
| POST | `/api-keys/{key_id}/revoke` | revoke |

## Repositories (GitHub gateway)

All require an authenticated user with a connected GitHub account; scopes are
enforced server-side. Every route forwards to GitHub REST unless noted.

| Method | Path |
|---|---|
| GET | `/repositories` |
| GET | `/repositories/{owner}/{repo}` |
| GET | `/repositories/{owner}/{repo}/branches` |
| GET | `/repositories/{owner}/{repo}/commits` |
| GET | `/repositories/{owner}/{repo}/pulls` |
| GET | `/repositories/{owner}/{repo}/pulls/{number}` |
| GET | `/repositories/{owner}/{repo}/issues` |
| GET | `/repositories/{owner}/{repo}/issues/{number}` |
| GET | `/repositories/{owner}/{repo}/releases` |
| GET | `/repositories/{owner}/{repo}/labels` |
| GET | `/repositories/{owner}/{repo}/milestones` |
| GET | `/repositories/{owner}/{repo}/workflows` |
| GET | `/repositories/{owner}/{repo}/actions/runs` |
| GET | `/repositories/{owner}/{repo}/collaborators` |
| GET | `/repositories/{owner}/{repo}/teams` |
| GET | `/repositories/{owner}/{repo}/discussions` (GraphQL) |
| GET | `/repositories/orgs` |
| POST | `/repositories` (create) |
| POST | `/repositories/{owner}/{repo}/forks` |
| DELETE | `/repositories/{owner}/{repo}` |
| POST | `/repositories/{owner}/{repo}/branches` |
| POST | `/repositories/{owner}/{repo}/merges` |
| POST | `/repositories/{owner}/{repo}/pulls` |
| PUT | `/repositories/{owner}/{repo}/pulls/{number}/merge` |
| POST | `/repositories/{owner}/{repo}/issues` |
| PATCH | `/repositories/{owner}/{repo}/issues/{number}` |
| POST | `/repositories/{owner}/{repo}/issues/{number}/close` |
| POST | `/repositories/{owner}/{repo}/issues/{number}/comments` |
| POST | `/repositories/{owner}/{repo}/releases` |
| POST | `/repositories/{owner}/{repo}/labels` |
| POST | `/repositories/{owner}/{repo}/milestones` |
| POST | `/repositories/{owner}/{repo}/actions/dispatch` |
| POST | `/repositories/graphql` (arbitrary GraphQL, scoped) |

## Audit

| Method | Path | Notes |
|---|---|---|
| GET | `/audit` | current user's audit events, paginated, `security_admin` for global view |

## Common errors

| code | HTTP | meaning |
|---|---|---|
| `validation_error` | 422 | request schema |
| `unauthorized` | 401 | no/invalid session |
| `csrf_failed` | 403 | bad `X-CSRF-Token` |
| `oauth_state_mismatch` / `oauth_state_expired` | 403 | OAuth state replay/expiry |
| `redirect_uri_mismatch` | 403 | bad redirect target |
| `pkce_validation_failed` | 403 | verifier/challenge mismatch |
| `account_linking_required` | 409 | GitHub email matches an existing password user |
| `rate_limited` | 429 | with `Retry-After` |
| `github_error` / `github_rate_limited` | 502/503 | upstream GitHub failure |
| `internal_error` | 500 | unhandled; logged w/ request_id |
