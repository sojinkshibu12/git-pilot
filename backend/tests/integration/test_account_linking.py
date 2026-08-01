"""Integration tests: GitHub→Password account linking."""
from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import select

STRONG_PASSWORD = "Str0ng-Passw0rd!-2026"


def _register_gh_user(fake_github, gh_id: int, login: str, email: str) -> None:
    fake_github.users[gh_id] = {
        "id": gh_id,
        "login": login,
        "name": login.title(),
        "avatar_url": None,
        "html_url": f"https://github.com/{login}",
        "email": email,
        "type": "User",
    }


def _challenge_from_url(url: str) -> str:
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(url).query)
    return qs["code_challenge"][0]


def _code_for(challenge: str) -> str:
    return f"gho_{hashlib.sha256(challenge.encode()).hexdigest()}"


@pytest.mark.asyncio
async def test_linking_required_when_email_exists(client, fake_github):
    # Existing password account with the same email.
    await client.post(
        "/api/v1/auth/register",
        json={"email": "shared@example.com", "password": STRONG_PASSWORD},
    )
    _register_gh_user(fake_github, 5001, "newgithub", "shared@example.com")

    auth_url, state = await _begin(client)
    challenge = _challenge_from_url(auth_url)
    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": state, "code": _code_for(challenge)},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "status=link_required" in resp.headers["location"]
    # A link_token is issued.
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(resp.headers["location"]).query)
    assert "link_token" in qs


@pytest.mark.asyncio
async def test_complete_link_with_correct_password(client, fake_github):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "linkme@example.com", "password": STRONG_PASSWORD},
    )
    _register_gh_user(fake_github, 5002, "githubuser", "linkme@example.com")

    auth_url, state = await _begin(client)
    challenge = _challenge_from_url(auth_url)
    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": state, "code": _code_for(challenge)},
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(resp.headers["location"]).query)
    link_token = qs["link_token"][0]

    resp = await client.post(
        "/api/v1/oauth/link/complete",
        json={
            "link_token": link_token,
            "password": STRONG_PASSWORD,
            "email": "linkme@example.com",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["login"] == "githubuser"


@pytest.mark.asyncio
async def test_complete_link_wrong_password_rejected(client, fake_github):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "wronglink@example.com", "password": STRONG_PASSWORD},
    )
    _register_gh_user(fake_github, 5003, "githubuser2", "wronglink@example.com")

    auth_url, state = await _begin(client)
    challenge = _challenge_from_url(auth_url)
    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": state, "code": _code_for(challenge)},
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(resp.headers["location"]).query)
    link_token = qs["link_token"][0]

    resp = await client.post(
        "/api/v1/oauth/link/complete",
        json={"link_token": link_token, "password": "Totally-Wrong-Password", "email": "wronglink@example.com"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_reused_link_token_rejected(client, fake_github):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "reuse@example.com", "password": STRONG_PASSWORD},
    )
    _register_gh_user(fake_github, 5004, "githubuser3", "reuse@example.com")

    auth_url, state = await _begin(client)
    challenge = _challenge_from_url(auth_url)
    resp = await client.get(
        "/api/v1/oauth/github/callback",
        params={"state": state, "code": _code_for(challenge)},
        follow_redirects=False,
    )
    from urllib.parse import parse_qs, urlparse

    qs = parse_qs(urlparse(resp.headers["location"]).query)
    link_token = qs["link_token"][0]

    ok = await client.post(
        "/api/v1/oauth/link/complete",
        json={"link_token": link_token, "password": STRONG_PASSWORD, "email": "reuse@example.com"},
    )
    assert ok.status_code == 200

    again = await client.post(
        "/api/v1/oauth/link/complete",
        json={"link_token": link_token, "password": STRONG_PASSWORD, "email": "reuse@example.com"},
    )
    assert again.status_code == 403


async def _begin(client) -> tuple[str, str]:
    resp = await client.get("/api/v1/oauth/github/begin")
    assert resp.status_code == 200
    data = resp.json()
    return data["authorize_url"], data["state"]
