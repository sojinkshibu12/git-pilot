# OAuth 2.1 Authorization Code + PKCE — Sequence

Based on RFC 6749 (with OAuth 2.1 updates), RFC 7636 (PKCE), and GitHub's
"Web application flow". **Implicit flow is never used.**

## Happy path — first-time GitHub sign-in

```
Browser            Frontend (Next)        Backend (FastAPI)            GitHub
   │                     │                       │                       │
   │ 1. click "GitHub"   │                       │                       │
   │────────────────────►│                       │                       │
   │                     │ 2. GET /oauth/github/begin                    │
   │                     │──────────────────────►│                       │
   │                     │                       │ 3. state = token_urlsafe(32)│
   │                     │                       │ 4. verifier → challenge (S256)│
   │                     │                       │ 5. persist OAuthState (hash)  │
   │                     │                       │    + PKCEChallenge (encrypted)│
   │                     │                       │ 6. build authorize URL        │
   │                     │ 7. {authorize_url}    │                       │
   │                     │◄──────────────────────│                       │
   │ 8. redirect (303)   │                       │                       │
   │────────────────────────────────────────────────────────────────────►│
   │                     │                       │ 9. user authorizes + consents│
   │                     │                       │ 10. 302 back w/ ?code&state  │
   │◄────────────────────────────────────────────────────────────────────│
   │                     │ 11. GET /oauth/github/callback?code&state      │
   │                     │──────────────────────►│                       │
   │                     │                       │ 12. hash state; constant-time│
   │                     │                       │     compare to stored        │
   │                     │                       │ 13. TTL ≤ 10 min? consumed?   │
   │                     │                       │ 14. redirect_uri == registered│
   │                     │                       │ 15. decrypt verifier; recompute│
   │                     │                       │     challenge; compare S256    │
   │                     │                       │ 16. POST /login/oauth/access_token│
   │                     │                       │     (client_id+secret+code+   │
   │                     │                       │      verifier)              │
   │                     │                       │◄─────────────────────────────│
   │                     │                       │ 17. access_token (backend only)│
   │                     │                       │ 18. GET /user, /user/emails   │
   │                     │                       │ 19. upsert User + GitHubAccount│
   │                     │                       │ 20. encrypt token (AES-256-GCM)│
   │                     │                       │ 21. create Session (DB + Redis)│
   │                     │                       │ 22. Set-Cookie: gp_session     │
   │                     │ 23. 303 → /auth/callback?status=success        │
   │                     │◄──────────────────────│                       │
   │ 24. redirect to /dashboard                 │                       │
```

## Account linking (GitHub sign-in collides with an existing email)

```
... up to step 17 identical ...
   │                     │                       │ 18. existing User w/ same email │
   │                     │                       │ 19. encrypt token → Redis       │
   │                     │                       │     gp:link:<token> (TTL 10 min)│
   │                     │ 20. 409 account_linking_required {link_token} │
   │                     │◄──────────────────────│                       │
   │ 21. render "Link existing account" screen  │                       │
   │ 22. user enters password of existing acct  │                       │
   │ 23. POST /oauth/link/complete {link_token, password, email}        │
   │                     │──────────────────────►│                       │
   │                     │                       │ 24. verify password (Argon2id)  │
   │                     │                       │ 25. attach GitHubAccount        │
   │                     │                       │ 26. store credential (encrypted)│
   │                     │                       │ 27. 200 → dashboard            │
```

## Failure handling

| Condition | Where detected | Response |
|---|---|---|
| `state` mismatch | callback step 12 | 403 `oauth_state_mismatch` + audit |
| `state` expired (>10 min) | callback step 13 | 403 `oauth_state_expired` + audit |
| `state` already consumed (replay) | callback step 13 | 403 `oauth_state_mismatch` + audit |
| `redirect_uri` mismatch | callback step 14 | 403 `redirect_uri_mismatch` + audit |
| PKCE verifier mismatch | callback step 15 | 403 `pkce_validation_failed` + audit |
| user cancelled | GitHub `error=access_denied` | 303 → `?status=cancelled` |
| GitHub down / rate limited | token exchange / API | 502 / 503 normalized |

## Security properties

- **State:** server-bound, single-use, 10-minute TTL, constant-time comparison,
  stored hashed (defense in depth).
- **PKCE:** S256 challenge issued at `begin`; verifier stored **encrypted**;
  validated before every code exchange; challenge is single-use.
- **Code exchange:** backend-only, never visible to JS. `client_secret` exists
  only in backend env vars.
- **Redirect URI:** exact-match only; no wildcards; validated per request.
- **Token storage:** AES-256-GCM (nonce + tag per ciphertext), versioned
  (`v1.`), rotation-ready.
- **Sessions:** opaque token in `HttpOnly` + `Secure` + `SameSite=Lax` cookie;
  server-side record in Redis + Postgres; rotation on timer; absolute + idle
  TTLs; global logout.
