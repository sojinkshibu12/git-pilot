# Database schema (ER)

PostgreSQL 16. All tables use **UUID PKs**, `created_at`/`updated_at`, and soft
deletes via `deleted_at` where noted. Source of truth: `backend/app/domain/models/`.
Migrations: `backend/alembic/versions/0001_initial.py`.

```
users ──┬─< github_accounts ──< github_credentials   (encrypted token vault)
        │                    └─< refresh_tokens
        ├─< sessions
        ├─< oauth_states ──< pkce_challenges
        ├─< api_keys
        ├─< user_preferences
        ├─< audit_logs
        ├─< repositories  ──< repository_permissions
        ├─< organization_members >─ organizations
        │
        └─< webhook_installations (per repo/org)
```

## Entities

### users
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| email | varchar(320) | unique on `lower(email)` |
| email_verified | bool | |
| password_hash | text | Argon2id |
| status | user_status | active / disabled / pending_email / locked / deleted |
| mfa_enabled, locale, plan | | |
| created_at / updated_at / deleted_at | timestamptz | |

### github_accounts
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK→users | |
| github_id | int | **canonical external identity**, unique |
| login, display_name, avatar_url | | mutable cache |
| email, email_verified, html_url, location, bio, company | | |
| github_type, plan, organizations_json | | |
| followers/following/public_repos | int | |
| unique(user_id, github_id) | | |

### github_credentials
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| github_account_id | uuid FK | |
| user_id | uuid FK | |
| is_active | bool | rotation — one active row per account |
| access_token_encrypted | text | AES-256-GCM (never plaintext) |
| refresh_token_encrypted | text \| null | |
| scopes | varchar(512) | space-separated granted scopes |
| expires_at / refresh_expires_at | timestamptz | |
| encryption_metadata | json | {algorithm, key_id} |
| token_version | int | |

### sessions
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| user_id | uuid FK | |
| session_token_hash | text unique | raw token never stored |
| csrf_token_hash | text | server-bound CSRF |
| status | session_status | active / revoked / expired / terminated |
| expires_at, last_used_at, rotated_at | timestamptz | absolute + idle TTL |
| ip_address, user_agent, device_label | | PII-reduced |
| is_current | bool | |
| revoked_reason | varchar | |

### oauth_states
| column | type | notes |
|---|---|---|
| id | uuid PK | |
| state_hash | text unique | SHA-256 of state nonce |
| session_id, user_id | uuid | binding |
| provider, flow_stage | | github; initiated→…→completed |
| scope, redirect_uri | | exact redirect stored |
| pkce_challenge_hash, pkce_method | | S256 |
| link_to_user_id | uuid | linking flows |
| expires_at (indexed) | | 10-min TTL |
| consumed_at | | single-use / replay defense |

### pkce_challenges
| column | type | notes |
|---|---|---|
| state_id | uuid FK unique | 1:1 with oauth_states |
| code_challenge_hash | text | SHA-256 of S256 challenge |
| code_verifier_encrypted | text | encrypted verifier |
| consumed_at | | deleted post-exchange |

### organizations / organization_members / repositories / repository_permissions
Mirror GitHub upstream: org metadata, user membership, repo metadata
(`github_id` unique, `full_name` unique), and per-user repo permissions
(`permission`: none/read/triage/write/maintain/admin).

### webhook_installations
Webhook delivery endpoints per repo/org with **encrypted** webhook secret,
enabled events, delivery status.

### refresh_tokens / api_keys
Server-side refresh token records (hashed) and API keys (prefixed, SHA-256
hash; the plaintext `gp_…` is shown exactly once).

### audit_logs
Append-only event stream: event_type (indexed), user_id/github_id, session_id,
request_id, correlation_id, ip_address, user_agent, severity, outcome,
resource_type/id, action, json metadata, created_at (indexed). Composite
indexes for `(user_id, event_type, created_at)` and `(correlation_id, created_at)`.

## Conventions
- UUIDs generated app-side (no `gen_random_uuid()` dependency).
- Soft delete via `deleted_at` on identity/repo entities; hard delete for
  one-shot records (PKCE, oauth_states cleanup job).
- `server_default` used for timestamps → Alembic `autogenerate` stays clean.
- Naming: `fk_<table>_<column>_<ref>`, `ix_...`, `uq_...` via naming convention.
