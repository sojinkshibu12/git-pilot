"""Integration tests: contribution heatmap aggregation, streaks, statistics."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.application.services.audit_service import AuditService
from app.application.services.contribution_service import ContributionService
from app.core.exceptions import TokenInvalidError
from app.domain.models.contributions import Contribution
from app.domain.models.identity import User


class FakeTokens:
    def __init__(self, login: str | None = "dev") -> None:
        self._login = login

    async def access_token_for_user(self, user_id):
        if not self._login:
            raise TokenInvalidError("No linked GitHub account.")
        return "test-token"

    async def github_login_for_user(self, user_id):
        return self._login


@pytest.fixture
async def db_session(app):
    db = app.state.db
    async with db.session_factory() as session:
        yield session


def _make_service(session, github, redis, tokens) -> ContributionService:
    return ContributionService(
        db=session,
        github=github,
        tokens=tokens,
        audit=AuditService(session),
        redis=redis,
    )


async def _make_user(session) -> User:
    user = User(email=f"contrib-{uuid.uuid4().hex[:12]}@example.com", display_name="Contrib")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _calendar(days: dict[str, int]) -> dict:
    return {
        "days": [{"date": d, "count": c} for d, c in days.items()],
        "total": sum(days.values()),
        "breakdown": {
            "commits": 0,
            "pull_requests": 0,
            "issues": 0,
            "reviews": 0,
            "repositories": 0,
            "actions": 0,
        },
    }


@pytest.mark.asyncio
async def test_get_year_empty_when_no_github_account(db_session, fake_github, fake_redis):
    user = await _make_user(db_session)
    service = _make_service(db_session, fake_github, fake_redis, FakeTokens(login=None))
    payload = await service.get_year(user.id, 2026)
    assert payload["connected"] is False
    assert payload["days"] == []
    assert payload["total"] == 0


@pytest.mark.asyncio
async def test_get_year_aggregates_from_calendar(db_session, fake_github, fake_redis):
    user = await _make_user(db_session)

    async def fake_calendar(token, login, from_date, to_date):
        return _calendar({"2026-01-01": 2, "2026-01-03": 5, "2026-01-05": 12})

    async def fake_commits(token, login, from_date, to_date):
        return {"2026-01-01": 2, "2026-01-03": 1}, {"acme/one": 3}

    fake_github.get_contribution_calendar = fake_calendar
    fake_github.get_commit_contribution_days = fake_commits

    service = _make_service(db_session, fake_github, fake_redis, FakeTokens("dev"))
    payload = await service.get_year(user.id, 2026)

    assert payload["connected"] is True
    assert payload["total"] == 19
    assert payload["max"] == 12
    by_date = {d["date"]: d for d in payload["days"]}
    assert by_date["2026-01-01"]["count"] == 2
    assert by_date["2026-01-01"]["level"] == 1
    assert by_date["2026-01-03"]["level"] == 2
    assert by_date["2026-01-05"]["level"] == 4
    assert by_date["2026-01-01"]["commits"] == 2
    start, end = ContributionService._window_bounds(2026)
    assert len(payload["days"]) == (end - start).days + 1


@pytest.mark.asyncio
async def test_streaks_computed(db_session, fake_github, fake_redis):
    user = await _make_user(db_session)
    # Jan 3–5 + Jan 7–9 (two 3-day runs); today (Aug) has no rows → current 0.
    for d in (date(2026, 1, 3), date(2026, 1, 4), date(2026, 1, 5),
              date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)):
        db_session.add(Contribution(user_id=user.id, date=d, count=1))
    await db_session.commit()

    service = _make_service(db_session, fake_github, fake_redis, FakeTokens("dev"))
    streaks = await service.get_streaks(user.id, 2026)
    assert streaks["longest_streak"] == 3
    assert streaks["current_streak"] == 0


@pytest.mark.asyncio
async def test_statistics_computed(db_session, fake_github, fake_redis):
    user = await _make_user(db_session)
    rows = [
        (date(2026, 1, 3), 2, 1, 1, 0, 0, 0, 0),
        (date(2026, 1, 10), 3, 0, 0, 1, 0, 0, 0),
        (date(2026, 2, 3), 1, 0, 0, 0, 0, 0, 0),
    ]
    for d, count, cm, pr, iss, rv, repo, act in rows:
        db_session.add(Contribution(
            user_id=user.id, date=d, count=count,
            commit_count=cm, pull_request_count=pr, issue_count=iss,
            review_count=rv, repository_count=repo, action_count=act,
        ))
    await db_session.commit()
    fake_redis._data["gh:contribrepo:dev:current"] = (
        '{"repos": [{"full_name": "acme/one", "count": 3}]}'
    )

    service = _make_service(db_session, fake_github, fake_redis, FakeTokens("dev"))
    stats = await service.get_statistics(user.id, 2026)

    assert stats["total"] == 6
    assert stats["days_contributed"] == 3
    assert stats["most_active_month"] == 1
    assert stats["breakdown"]["commits"] == 1
    assert stats["breakdown"]["pull_requests"] == 1
    assert stats["breakdown"]["issues"] == 1
    assert stats["most_active_repository"]["full_name"] == "acme/one"


@pytest.mark.asyncio
async def test_refresh_reaggregates(db_session, fake_github, fake_redis):
    user = await _make_user(db_session)
    calls = {"n": 0}

    async def fake_calendar(token, login, from_date, to_date):
        calls["n"] += 1
        return _calendar({"2026-01-01": 1})

    fake_github.get_contribution_calendar = fake_calendar
    service = _make_service(db_session, fake_github, fake_redis, FakeTokens("dev"))

    first = await service.get_year(user.id, 2026)
    assert first["total"] == 1
    assert calls["n"] == 1

    # Second read is served from the DB — no new GitHub call.
    second = await service.get_year(user.id, 2026)
    assert second["total"] == 1
    assert calls["n"] == 1

    # Forced refresh re-aggregates.
    ok = await service.refresh(user.id, 2026)
    assert ok is True
    assert calls["n"] == 2
    await db_session.commit()
