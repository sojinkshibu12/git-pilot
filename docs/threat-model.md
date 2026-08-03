# Threat model

Threat modeling methodology: **STRIDE per trust boundary**, with a data-flow
orientation. Assets, trust boundaries, threats, mitigations, and residual risk
are tracked below. Revisit after every change to the OAuth or session path.

## Assets
1. GitHub access tokens (OAuth `access_token`; may include `repo`, `write:*`)
2. Refresh tokens
3. User passwords / Argon2id hashes
4. Session tokens & CSRF tokens
5. `SECRET_KEY` / GitHub `client_secret`
6. User PII (email, IP, user-agent, avatar URL)
7. Audit log integrity
8. Webhook secrets

## Trust boundaries
- **B0** External Internet → Nginx/Frontend
- **B1** Frontend → API (browser context, JS-visible data)
- **B2** API → PostgreSQL
- **B3** API → Redis
- **B4** API → GitHub
- **B5** Admin/operator access (SSH, CI, vault)

## Threats (ranked)

| # | Threat | STRIDE | Boundary | Risk | Mitigation | Status |
|---|---|---|---|---|---|---|
| T1 | Access token exfiltration via XSS | S/I | B1 | **Critical** | Tokens never in JS; HttpOnly cookie; strict CSP; React escapes HTML; no `dangerouslySetInnerHTML` in token paths | Implemented |
| T2 | Session hijack (cookie theft) | S | B0 | Critical | Secure+HttpOnly+SameSite=Lax, TLS, rotation, absolute/idle TTL, reuse detection, IP anomaly audit | Implemented |
| T3 | CSRF on mutating endpoints | E | B0 | High | Per-session CSRF token (header) + Origin/Referer + SameSite=Lax + JSON content-type guard | Implemented |
| T4 | OAuth `state` fix/CSRF on callback | S/E | B0 | Critical | Random state, hash at rest, constant-time compare, single-use, 10-min TTL, session-bound | Implemented |
| T5 | PKCE downgrade / verifier leak | S | B0 | High | S256 enforced, verifier encrypted, single-use challenge, no `plain` method | Implemented |
| T6 | Auth-code replay | E | B0 | High | State single-use; code exchange once; PKCE binds code to initial request | Implemented |
| T7 | Open redirect via `redirect_uri` | I | B0 | High | Exact-match whitelist, validated twice, absolute URI only | Implemented |
| T8 | `client_secret` leak | S | B0/B1 | Critical | Server-side exchange only, env-injected, never in bundle/logs | Implemented |
| T9 | DB leak → token plaintext | S | B2 | Critical | AES-256-GCM vault, AAD binding, key separate from DB | Implemented |
| T10 | DB leak → passwords | S | B2 | High | Argon2id with per-user salt; no reversible form | Implemented |
| T11 | Brute-force / credential stuffing | E | B0 | High | Rate limits, backoff, lockout, audit | Implemented |
| T12 | Redis compromise → session forgery | S | B3 | High | Token hash-bound to DB row; Redis stores derived tokens only; short TTL; DB cross-check on privilege ops | Partially — document gap |
| T13 | Privilege escalation via crafted GraphQL | E | B1 | High | Scoped tokens, server-side permission mapping, least-privilege proxy | Implemented |
| T14 | Audit log tampering | T | B2 | High | Append-only table, no update/delete API, SIEM export, hash-chaining (backlog) | Partial |
| T15 | Token rotation race (refresh storm) | D | B2/B3 | Medium | Unique active-credential constraint; idempotent rotation; short lock via Redis | Implemented |
| T16 | Webhook spoofing | S | B0 | Medium | Shared-secret HMAC verification, IP allowlist (backlog) | Partial |
| T17 | DoS via OAuth begin / repos proxy | D | B0 | Medium | Per-IP/user rate limits, GitHub rate-limit passthrough | Implemented |
| T18 | Log injection | I | B2 | Low | Structured JSON logging, newline/CR sanitization | Implemented |
| T19 | Session fixation | E | B1 | High | Token regenerated on login (rotation); no pre-auth session reuse | Implemented |
| T20 | IDOR on user/repo data | E | B1 | High | Ownership scoping in `RepositoryService`; GUID ids; row-level checks | Implemented |

## Residual risk & backlog
- **T12 gap:** Redis compromise could serve valid session records briefly.
  Mitigate with DB round-trip on sensitive operations or encrypted-at-rest Redis.
- **T14:** hash-chaining of audit rows not yet implemented.
- **T16:** GitHub IP allowlist for webhooks pending.
- **Passwords** are uncrackable at scale but still subject to credential
  stuffing — keep email breach monitoring and MFA enablement high priority.

## Assumptions
- TLS terminated at Nginx; backend never exposed directly.
- Operators rotate `SECRET_KEY` and GitHub secrets per incident policy.
- GitHub App mode (`GITHUB_APP_TYPE=github_app`) uses least-privileged
  installation tokens for repo-scoped operations; T13 mitigation is strongest
  in that mode.
