"""Integration tests: full OAuth Authorization Code + PKCE flow (mock GitHub)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.domain.models.identity import AuditLog, OAuthState


async def _begin_flow(client, fake_redis) -> tuple[str, str]:
    resp = await client.get("/api/v1/oauth/github/begin")
    assert resp.status_code == 200
    data = resp.json()
    assert "authorize_url" in data
    assert data["pkce_method"] == "S256"
    assert "github.com/login/oauth/authorize" in data["authorize_url"]
    assert "code_challenge_method=S256" in data["authorize_url"]
    state = data["state"]
    # Pull stored PKCE verifier from our fake DB to simulate a legit callback.
    # The service stores an encrypted verifier; tests can't easily read it, so we
    # compute the challenge from the authorize URL instead.
    return data["authorize_url"], state


def _challenge_from_url(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    return qs["code_challenge"][0]


def _token_for(challenge: str) -> str:
    return f"gho_{hashlib.sha256(challenge.encode()).hexdigest()}"


def _register_gh_user(fake_github, gh_id: int, login: str, email: str) -> None:
    fake_github.users[gh_id] = {
        "id": gh_id,
        "login": login,
        "name": login.title(),
        "avatar_url": None,
        "html_url": f"https://github.com/{login}",
        "email": email,
        "type": "User",
        "email_verified": True,
    }


@pytest.mark.asyncio
async def test_full_oauth_login_creates_user_and_sets_cookie(client, fake_github, settings):
    _register_gh_user(fake_github, 1001, "octocat", "octo@example.com")
    auth_url, state = await _begin_flow(client, None)
    challenge = _challenge_from_url(auth_url)

    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={
            "state": state,
            "code": _token_for(challenge),
            "scope": "read:user user:email repo",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "location" in resp.headers
    assert "status=success" in resp.headers["location"]
    assert "gp_session" in resp.cookies

    # Session cookie is present and user is created.
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["email"] == "octo@example.com"


@pytest.mark.asyncio
async def test_callback_state_mismatch_returns_403(client, fake_github, settings, app):
    _register_gh_user(fake_github, 1002, "mallory", "m@example.com")
    await _begin_flow(client, None)

    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": "attacker-controlled-state", "code": "code"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "oauth_state_mismatch"

    # Audit log must record the mismatch.
    db = app.state.db
    async with db.session_factory() as session:
        rows = (
            await session.scalars(
                select(AuditLog).where(AuditLog.event_type == "oauth.state_mismatch")
            )
        ).all()
    assert len(rows) >= 1


async def _get_audit(client):
    return {"events": []}


@pytest.mark.asyncio
async def test_callback_state_expired_returns_403(client, fake_github, settings, app):
    _register_gh_user(fake_github, 1003, "delayed", "d@example.com")
    auth_url, state = await _begin_flow(client, None)
    challenge = _challenge_from_url(auth_url)

    # Force-expire the state row.
    db = app.state.db
    async with db.session_factory() as session:
        row = await session.scalar(select(OAuthState))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": state, "code": _token_for(challenge)},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "oauth_state_expired"


@pytest.mark.asyncio
async def test_callback_replay_is_rejected(client, fake_github, settings):
    _register_gh_user(fake_github, 1004, "replay", "r@example.com")
    auth_url, state = await _begin_flow(client, None)
    challenge = _challenge_from_url(auth_url)
    code = _token_for(challenge)

    first = await client.get("/api/v1/oauth/github/callback", params={"state": state, "code": code})
    assert first.status_code == 303

    second = await client.get(
        "/api/v1/oauth/github/callback", params={"state": state, "code": code}
    )
    assert second.status_code == 403
    assert second.json()["code"] == "oauth_state_mismatch"


@pytest.mark.asyncio
async def test_callback_access_denied_is_mapped(client, fake_github):
    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": "whatever", "error": "access_denied"},
    )
    assert resp.status_code == 303
    assert "status=cancelled" in resp.headers["location"]


@pytest.mark.asyncio
async def test_pkce_verifier_mismatch_rejected(client, fake_github, settings, app):
    """Simulate a callback whose PKCE verifier does not match the challenge."""
    _register_gh_user(fake_github, 1005, "pkce", "p@example.com")
    auth_url, state = await _begin_flow(client, None)

    # Corrupt the stored challenge hash so validation fails deterministically.
    from app.domain.models.identity import PKCEChallenge

    db = app.state.db
    async with db.session_factory() as session:
        row = await session.scalar(select(PKCEChallenge))
        row.code_challenge_hash = hashlib.sha256(b"tampered").hexdigest()
        await session.commit()

    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": state, "code": "some-code"},
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "pkce_validation_failed"


@pytest.mark.asyncio
async def test_missing_email_resolved_from_user_emails(client, fake_github):
    gh_id = 2001
    fake_github.users[gh_id] = {
        "id": gh_id,
        "login": "noemail",
        "name": None,
        "avatar_url": None,
        "html_url": "",
        "email": None,
        "type": "User",
    }
    fake_github.emails = [
        {
            "email": "verified-primary@example.com",
            "primary": True,
            "verified": True,
            "visibility": "private",
        },
    ]
    auth_url, state = await _begin_flow(client, None)
    challenge = _challenge_from_url(auth_url)

    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": state, "code": _token_for(challenge)},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    me = await client.get("/api/v1/users/me")
    assert me.json()["email"] == "verified-primary@example.com"
