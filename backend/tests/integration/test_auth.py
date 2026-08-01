"""Integration tests: password registration/login + session management."""
from __future__ import annotations

import pytest

from app.core.security import generate_verifier

STRONG_PASSWORD = "Str0ng-Passw0rd!-2026"


@pytest.mark.asyncio
async def test_register_login_logout_flow(client):
    # Register
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dev@example.com",
            "password": STRONG_PASSWORD,
            "display_name": "Dev User",
        },
    )
    assert resp.status_code == 201
    token = resp.json()["data"]["verification_token"]
    assert token

    # Login before verification should still work (status gate is lenient in dev)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "dev@example.com", "password": STRONG_PASSWORD},
    )
    assert resp.status_code == 200
    assert "gp_session" in resp.cookies
    profile = resp.json()
    assert profile["email"] == "dev@example.com"

    # Me endpoint
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 200
    assert me.json()["email"] == "dev@example.com"

    # Logout
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200

    # Session is gone
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_duplicate_registration_rejected(client):
    payload = {"email": "dup@example.com", "password": STRONG_PASSWORD}
    assert (await client.post("/api/v1/auth/register", json=payload)).status_code == 201
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 409
    assert resp.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_weak_password_rejected(client):
    resp = await client.post(
        "/api/v1/auth/register", json={"email": "weak@example.com", "password": "short"}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "wrongpw@example.com", "password": STRONG_PASSWORD}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "wrongpw@example.com", "password": "Wrong-Password-1"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_failed"


@pytest.mark.asyncio
async def test_verify_email(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "verify@example.com", "password": STRONG_PASSWORD},
    )
    token = resp.json()["data"]["verification_token"]

    resp = await client.post("/api/v1/auth/email/verify", json={"token": token})
    assert resp.status_code == 200
    assert "verified" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_password_change_requires_csrf(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "change@example.com", "password": STRONG_PASSWORD}
    )
    await client.post("/api/v1/auth/login", json={"email": "change@example.com", "password": STRONG_PASSWORD})

    # CSRF is required on mutating endpoints.
    resp = await client.post(
        "/api/v1/auth/password/change",
        json={"current_password": STRONG_PASSWORD, "new_password": "New-Str0ng-Pass-2026!"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_failed" or resp.json()["code"] == "csrf"


@pytest.mark.asyncio
async def test_rate_limiting_on_login(client):
    for _ in range(15):
        await client.post(
            "/api/v1/auth/login",
            json={"email": "ratelimited@example.com", "password": "Wrong-Password-1"},
        )
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "ratelimited@example.com", "password": "Wrong-Password-1"},
    )
    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_session_expired_returns_401(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "expire@example.com", "password": STRONG_PASSWORD}
    )
    await client.post("/api/v1/auth/login", json={"email": "expire@example.com", "password": STRONG_PASSWORD})
    # Force-invalidate by clearing the fake redis session store.
    from app.main import app

    app.state.redis._data.clear()
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 401
    assert me.json()["code"] == "session_expired"


@pytest.mark.asyncio
async def test_revoke_all_sessions(client):
    await client.post(
        "/api/v1/auth/register", json={"email": "revoke@example.com", "password": STRONG_PASSWORD}
    )
    await client.post("/api/v1/auth/login", json={"email": "revoke@example.com", "password": STRONG_PASSWORD})
    resp = await client.post("/api/v1/auth/logout-all")
    assert resp.status_code == 200
    me = await client.get("/api/v1/users/me")
    assert me.status_code == 401
