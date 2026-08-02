"""Integration tests: authenticated endpoint surface (users, sessions, api-keys,
audit, repositories, contributions, oauth errors)."""

from __future__ import annotations

import hashlib
import uuid

import pytest

from app.domain.models.github import GitHubCredential
from app.domain.models.identity import GitHubAccount

STRONG_PASSWORD = "Str0ng-Passw0rd!-2026"


async def _register_and_login(client) -> str:
    email = f"ep-{uuid.uuid4().hex[:12]}@example.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": STRONG_PASSWORD, "display_name": "EP User"},
    )
    assert resp.status_code == 201
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD}
    )
    assert resp.status_code == 200
    return email


async def _csrf_token(client) -> str:
    resp = await client.post("/api/v1/sessions/csrf")
    assert resp.status_code == 200
    return resp.json()["data"]["csrf_token"]


async def _link_github(app, user_email: str) -> None:
    """Attach a GitHub account + active credential so repo endpoints work."""
    db = app.state.db
    async with db.session_factory() as session:
        from sqlalchemy import select

        from app.domain.models.identity import User

        user = await session.scalar(select(User).where(User.email == user_email))
        account = GitHubAccount(user_id=user.id, github_id=4242, login="epuser", email=user_email)
        session.add(account)
        await session.flush()
        vault = app.state.vault
        cred = GitHubCredential(
            github_account_id=account.id,
            user_id=user.id,
            github_id=4242,
            is_active=True,
            access_token_encrypted=vault.encrypt("gho_ep_token"),
            scopes="repo",
            encryption_metadata={"algorithm": "aes-256-gcm", "key_id": "v1"},
            token_version=1,
        )
        session.add(cred)
        await session.commit()


@pytest.mark.asyncio
async def test_health_and_ready(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["database"] is True
    resp = await client.get("/api/v1/ready")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True


@pytest.mark.asyncio
async def test_users_profile_and_preferences(client):
    await _register_and_login(client)
    csrf = await _csrf_token(client)
    headers = {"X-CSRF-Token": csrf}

    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200

    patched = await client.patch(
        "/api/v1/users/me", json={"display_name": "Renamed"}, headers=headers
    )
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Renamed"

    prefs = await client.get("/api/v1/users/me/preferences")
    assert prefs.status_code == 200
    assert prefs.json()["theme"] == "system"

    prefs2 = await client.patch(
        "/api/v1/users/me/preferences", json={"theme": "dark"}, headers=headers
    )
    assert prefs2.status_code == 200
    assert prefs2.json()["theme"] == "dark"

    accounts = await client.get("/api/v1/users/me/connected-accounts")
    assert accounts.status_code == 200

    security = await client.get("/api/v1/users/me/security")
    assert security.status_code == 200


@pytest.mark.asyncio
async def test_sessions_list_and_revoke(client):
    email = await _register_and_login(client)
    resp = await client.get("/api/v1/sessions/")
    assert resp.status_code == 200
    assert len(resp.json()["sessions"]) == 1

    csrf = await _csrf_token(client)
    headers = {"X-CSRF-Token": csrf}
    session_id = resp.json()["sessions"][0]["id"]
    revoked = await client.post(f"/api/v1/sessions/{session_id}/revoke", headers=headers)
    assert revoked.status_code == 200

    # Re-login for a fresh session before revoke-all.
    await client.post("/api/v1/auth/login", json={"email": email, "password": STRONG_PASSWORD})
    csrf2 = await _csrf_token(client)
    resp2 = await client.post("/api/v1/sessions/revoke-all", headers={"X-CSRF-Token": csrf2})
    assert resp2.status_code == 200
    assert resp2.json()["revoked"] == 0


@pytest.mark.asyncio
async def test_api_keys_crud(client):
    await _register_and_login(client)
    csrf = await _csrf_token(client)
    headers = {"X-CSRF-Token": csrf}

    created = await client.post(
        "/api/v1/api-keys/", json={"name": "ci", "scopes": ["repos:read"]}, headers=headers
    )
    assert created.status_code == 201
    raw = created.json()["key"]
    assert raw.startswith("gp_")

    listed = await client.get("/api/v1/api-keys/")
    assert listed.status_code == 200
    key_id = listed.json()[0]["id"]

    revoked = await client.post(f"/api/v1/api-keys/{key_id}/revoke", headers=headers)
    assert revoked.status_code == 200
    after = await client.get("/api/v1/api-keys/")
    assert after.json() == []


@pytest.mark.asyncio
async def test_audit_list(client):
    await _register_and_login(client)
    resp = await client.get("/api/v1/audit/")
    assert resp.status_code == 200
    assert "events" in resp.json()


@pytest.mark.asyncio
async def test_repository_read_endpoints(client, app):
    email = await _register_and_login(client)
    await _link_github(app, email)

    assert (await client.get("/api/v1/repositories/")).status_code == 200
    assert (await client.get("/api/v1/repositories/?q=repo")).status_code == 200
    assert (await client.get("/api/v1/issues/assigned")).status_code == 200
    assert (await client.get("/api/v1/repositories/contributions")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/branches")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/commits")).status_code == 200
    resp = await client.get("/api/v1/repositories/acme/repo/commits/abc123")
    assert resp.status_code == 200
    assert resp.json()["files"][0]["filename"] == "src/app.py"
    assert (await client.get("/api/v1/repositories/acme/repo/pulls")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/pulls/1")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/issues")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/issues/1")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/releases")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/labels")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/milestones")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/workflows")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/actions/runs")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/collaborators")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/teams")).status_code == 200
    assert (await client.get("/api/v1/repositories/acme/repo/discussions")).status_code == 200
    assert (await client.get("/api/v1/repositories/orgs")).status_code == 200


@pytest.mark.asyncio
async def test_repository_write_endpoints(client, app):
    await _register_and_login(client)
    csrf = await _csrf_token(client)
    headers = {"X-CSRF-Token": csrf}

    email = (await client.get("/api/v1/users/me")).json()["email"]
    await _link_github(app, email)

    async def _post(url, json=None, **kw):
        return await client.post(url, json=json or {}, headers=headers, **kw)

    async def _patch(url, json=None):
        return await client.patch(url, json=json or {}, headers=headers)

    async def _put(url):
        return await client.put(url, json={}, headers=headers)

    async def _delete(url):
        return await client.delete(url, headers=headers)

    assert (await _post("/api/v1/repositories/", json={"name": "newrepo"})).status_code == 200
    assert (await _post("/api/v1/repositories/acme/repo/forks")).status_code == 200
    assert (
        await _post(
            "/api/v1/repositories/acme/repo/branches", json={"name": "feat", "from_sha": "s"}
        )
    ).status_code == 200
    assert (
        await _post("/api/v1/repositories/acme/repo/merges", json={"base": "main", "head": "feat"})
    ).status_code == 200
    assert (
        await _post(
            "/api/v1/repositories/acme/repo/pulls", json={"title": "T", "head": "f", "base": "m"}
        )
    ).status_code == 200
    assert (
        await _post("/api/v1/repositories/acme/repo/issues", json={"title": "I"})
    ).status_code == 200
    assert (
        await _post("/api/v1/repositories/acme/repo/issues/1/comments", json={"body": "hi"})
    ).status_code == 200
    assert (await _post("/api/v1/repositories/acme/repo/issues/1/close")).status_code == 200
    assert (
        await _post("/api/v1/repositories/acme/repo/releases", json={"tag_name": "v1"})
    ).status_code == 200
    assert (
        await _post(
            "/api/v1/repositories/acme/repo/labels", json={"name": "bug", "color": "d73a4a"}
        )
    ).status_code == 200
    assert (
        await _post("/api/v1/repositories/acme/repo/milestones", json={"title": "M1"})
    ).status_code == 200
    assert (
        await _post(
            "/api/v1/repositories/acme/repo/actions/dispatch",
            json={"workflow_id": "1", "ref": "main"},
        )
    ).status_code == 200

    assert (
        await _patch("/api/v1/repositories/acme/repo/issues/1", json={"state": "closed"})
    ).status_code == 200
    assert (await _put("/api/v1/repositories/acme/repo/pulls/1/merge")).status_code == 200
    assert (
        await _post("/api/v1/repositories/acme/repo/pulls/1/reviewers", json={"reviewers": ["bob"]})
    ).status_code == 200
    assert (
        await _post("/api/v1/repositories/acme/repo/pulls/1/reviews", json={"event": "APPROVE"})
    ).status_code == 200
    assert (
        await _post("/api/v1/repositories/graphql", json={"query": "{ viewer { login } }"})
    ).status_code == 200

    assert (await _delete("/api/v1/repositories/acme/repo")).status_code == 200


@pytest.mark.asyncio
async def test_contributions_endpoints(client, app):
    email = await _register_and_login(client)
    await _link_github(app, email)
    csrf = await _csrf_token(client)
    headers = {"X-CSRF-Token": csrf}

    year = 2026
    assert (await client.get(f"/api/v1/contributions/?year={year}")).status_code == 200
    resp = await client.get("/api/v1/contributions/streak", params={"year": year})
    assert resp.status_code == 200
    resp = await client.get("/api/v1/contributions/statistics", params={"year": year})
    assert resp.status_code == 200
    assert (await client.get(f"/api/v1/contributions/{year}")).status_code == 200
    assert (
        await client.post("/api/v1/contributions/refresh", json={"year": year}, headers=headers)
    ).status_code == 200

    # Bad year → validation failure.
    assert (await client.get("/api/v1/contributions/1900")).status_code == 422


@pytest.mark.asyncio
async def test_oauth_error_redirects(client):
    # Unknown state → security error raised by handler (403), audit preserved.
    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": "nope", "code": "c"},
        follow_redirects=False,
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "oauth_state_mismatch"

    # Cancelled by user → redirect with cancelled status.
    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"error": "access_denied"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "status=cancelled" in resp.headers["location"]


@pytest.mark.asyncio
async def test_oauth_complete_link_missing_fields(client):
    resp = await client.post("/api/v1/oauth/link/complete", json={})
    assert resp.status_code == 422

    resp = await client.post(
        "/api/v1/oauth/link/complete", json={"link_token": "x", "password": "y"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auth_resend_verification(client):
    email = await _register_and_login(client)
    resp = await client.post("/api/v1/auth/email/resend", json={"email": email})
    assert resp.status_code == 200
    assert resp.json()["data"]["verification_token"]

    resp = await client.post("/api/v1/auth/email/resend", json={"email": "nobody@example.com"})
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_auth_change_password_flow(client):
    await _register_and_login(client)
    csrf = await _csrf_token(client)
    headers = {"X-CSRF-Token": csrf}
    resp = await client.post(
        "/api/v1/auth/password/change",
        json={
            "current_password": STRONG_PASSWORD,
            "new_password": "Brand-New-Str0ng-Pass-2026!",
        },
        headers=headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_link_github_endpoint_rejected(client):
    await _register_and_login(client)
    resp = await client.post("/api/v1/auth/link/github", json={"code": "x"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_csrf_middleware_rejects_bad_origin(client):
    await _register_and_login(client)
    resp = await client.post(
        "/api/v1/api-keys/",
        json={"name": "x", "scopes": []},
        headers={"Origin": "https://evil.example"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unlink_github(client, app):
    email = await _register_and_login(client)
    await _link_github(app, email)
    csrf = await _csrf_token(client)
    headers = {"X-CSRF-Token": csrf}

    accounts = await client.get("/api/v1/users/me/connected-accounts")
    accs = accounts.json()["accounts"]
    assert any(a["provider"] == "github" and a["connected"] for a in accs)

    db = app.state.db
    async with db.session_factory() as session:
        from sqlalchemy import select

        from app.domain.models.identity import User

        me = await session.scalar(select(User).where(User.email == email))
        account = await session.scalar(
            select(GitHubAccount).where(
                GitHubAccount.user_id == me.id, GitHubAccount.deleted_at.is_(None)
            )
        )
        account_id = account.id
    resp = await client.post(f"/api/v1/users/me/unlink/github/{account_id}", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_csrf_token_missing_rejected(client):
    await _register_and_login(client)
    resp = await client.post("/api/v1/api-keys/", json={"name": "x", "scopes": []})
    assert resp.status_code == 401


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
