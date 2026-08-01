"""Playwright End-to-End tests for the auth experience.

Run:  playwright test   (from backend/ or frontend/, see playwright.config.ts)

Targets the Docker stack (frontend :3000, backend :8000) with a real GitHub
OAuth App configured for E2E.
"""
from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _goto(path: str, page: Page) -> None:
    page.goto(f"http://localhost:3000{path}", wait_until="networkidle")


def test_login_page_renders(page: Page) -> None:
    _goto("/login", page)
    expect(page.get_by_role("heading", name="Welcome back")).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("Continue with GitHub", re.I))).to_be_visible()


def test_register_page_renders(page: Page) -> None:
    _goto("/register", page)
    expect(page.get_by_role("heading", name="Create your account")).to_be_visible()


def test_github_button_starts_oauth(page: Page) -> None:
    _goto("/login", page)
    page.get_by_role("button", name=re.compile("Continue with GitHub", re.I)).click()
    # Redirects to GitHub authorize endpoint (may be blocked in CI without creds,
    # so we assert navigation started toward github.com).
    page.wait_for_url(re.compile(r"https?://github\.com/login/oauth/authorize.*code_challenge=S256"), timeout=15000)


def test_callback_success_shows_dashboard(page: Page) -> None:
    _goto("/auth/callback?provider=github&status=success", page)
    expect(page.get_by_text("Authenticated")).to_be_visible()


def test_callback_cancelled_shows_message(page: Page) -> None:
    _goto("/auth/callback?provider=github&status=cancelled", page)
    expect(page.get_by_text(re.compile("cancel", re.I))).to_be_visible()


def test_session_expired_screen(page: Page) -> None:
    _goto("/auth/expired", page)
    expect(page.get_by_text("Session expired")).to_be_visible()
    page.get_by_role("button", name=re.compile("Sign in again", re.I)).click()
    page.wait_for_url(re.compile(r"/login"), timeout=10000)


def test_invalid_link_leads_to_404(page: Page) -> None:
    _goto("/definitely-not-a-route", page)
    expect(page.get_by_text("404")).to_be_visible()


def test_dark_mode_toggle(page: Page) -> None:
    _goto("/login", page)
    if page.locator("[data-theme-toggle]").count():
        page.locator("[data-theme-toggle]").click()
        expect(page.locator("html")).to_have_attribute("class", re.compile(r"dark"))
