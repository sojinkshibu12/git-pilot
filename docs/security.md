# Security guide

Security-first by design. This document describes the controls, where they
live, and how to operate them safely.

## Threat model summary
Full threat model in `threat-model.md`. Key risks addressed: token theft,
session hijacking, CSRF, open-redirect via OAuth, PKCE downgrade, replay of
authorization codes, credential stuffing, privilege escalation, audit evasion.

## Authentication

### Password accounts
- **Hashing:** Argon2id (memory 19 MiB, time cost tuned), per-user salt.
  Implements `PasswordHasher` in `backend/app/core/security.py`.
- **Registration:** unique emails, optional email verification, 12-char
  minimum, strength checks.
- **Login throttling:** per-email and per-IP rate limits + exponential
  backoff; account lockout after N failures.

### GitHub OAuth (RFC 6749 + 7636)
- **State:** random 32-byte nonce; stored as SHA-256 hash bound to the user's
  session; **10-minute TTL**; **single-use** (replay rejected); verified with
  constant-time comparison.
- **PKCE:** S256 challenge; verifier encrypted at rest; challenge compared
  before code exchange; single-use.
- **Redirect URI:** exact-match whitelist; wildcards rejected; validated at
  `begin` and again at `callback`.
- **Code exchange:** happens server-side only; `client_secret` lives in env,
  never in the frontend or bundle.

## Token vault (AES-256-GCM)
`TokenVault` in `backend/app/core/security.py`:

- Encryption key derived from `SECRET_KEY` (see `environment.md`); no key is
  committed. For production set a **random 32-byte** `SECRET_KEY`.
- Ciphertext format: `v1.<nonce>.<ciphertext+tag>` (base64url). Nonce is
  unique per encryption; GCM tag authenticates ciphertext + AAD.
- AAD binds ciphertext to the owning `github_account_id` to prevent swap/replay.
- Storage columns are `*_encrypted`; `TokenService` is the only gate.
- **Rotation:** on GitHub token rotation a new credential row is written
  `is_active=true` and the previous row is deactivated.

## Sessions
`SessionService` + Redis `SessionStore`:

| Control | Value |
|---|---|
| Cookie | `gp_session`, `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/` |
| Transport | TLS 1.2+ enforced by Nginx |
| Server-side record | Redis (opaque token hash) + Postgres (session row) |
| Absolute TTL | `SESSION_TTL_HOURS` (default 7d) |
| Idle timeout | `SESSION_IDLE_MINUTES` (default 30m, sliding) |
| Rotation | on login, on privilege change, interval-based |
| Reuse detection | token-reuse alert on race conditions |
| Revocation | per-session + global (`POST /auth/logout-all`) |

The raw session token is never stored — only its SHA-256 hash.

## CSRF protection
- Per-session random CSRF token hashed server-side; the **plaintext** is
  delivered to the frontend via a dedicated endpoint/session bootstrap
  (never the hash — this is a deliberate fix in `app/api/dependencies.py`).
- All mutating endpoints require `X-CSRF-Token` header, verified with
  constant-time comparison against the session's hash.
- Origin/Referer header checks in `SecurityMiddleware` as a second layer;
  `SameSite=Lax` cookie as a third.
- JSON `Content-Type` enforced for mutating requests (no form auto-submit).

## Headers (Nginx + middleware)
`SecurityHeaders` middleware sets: `Content-Security-Policy`
(`default-src 'self'`), `X-Content-Type-Options: nosniff`, `X-Frame-Options:
DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`,
`Cross-Origin-Opener-Policy`, `HSTS` (behind TLS). The frontend adds CSP via
Next.js metadata where server-rendered.

## Rate limiting
Redis-backed fixed/sliding window in `backend/app/infrastructure/security/rate_limiter.py`
with per-user, per-IP, and per-endpoint buckets (login, register, OAuth begin,
repos proxy, audit export). 429 responses include `Retry-After`.

## Auditing
Every security-relevant action writes to `audit_logs` (append-only) and emits
a structured log line. `correlation_id` traces a full request; `request_id`
per request. Audit API is restricted to `security_admin` and paginated.

## Secret management
- **Never** commit `.env`; use the template and rotate in production.
- `SECRET_KEY`, GitHub `CLIENT_ID`/`CLIENT_SECRET`, `DATABASE_URL`,
  `REDIS_URL`, `WEBHOOK_SECRET` all env-driven via Pydantic Settings with
  strict validation at startup.
- Default development secret is disabled when `ENV=production` (startup fails
  unless overridden).

## Known hardening backlog
- [ ] Rate-limit `POST /oauth/link/complete` on password guesses.
- [ ] Hash PII in `user_agent` before long-term audit retention.
- [ ] Add GitHub IP-allowlist verification for webhook callbacks.
- [ ] Cron for `oauth_states`/`pkce_challenges` purge beyond TTL.
