"""Contribution service — aggregates GitHub activity into a heatmap.

The authoritative grid comes from GitHub's GraphQL `contributionsCollection`
(the same source as the GitHub profile heatmap) and is persisted per-day in the
`contributions` table. Per-type day-level breakdowns (commits / PRs / issues /
reviews / repository creations / actions) are best-effort aggregations so the
dashboard's filter toggles stay fast and never re-hit GitHub.

Every upstream error is mapped to a domain exception (or degrades to zeros for
the optional type breakdowns); a user without a linked GitHub account gets an
empty, `connected=false` response instead of an error.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.services.audit_service import AuditService
from app.application.services.token_service import TokenService
from app.core.exceptions import TokenInvalidError
from app.core.logging import get_logger
from app.domain.models.contributions import Contribution
from app.domain.models.enums import AuditEventType
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.github.exceptions import GitHubClientError, to_domain_exception
from app.infrastructure.redis.client import RedisClient

logger = get_logger("contributions")

_FIELD_BY_TYPE = {
    "commits": "commit_count",
    "pull_requests": "pull_request_count",
    "issues": "issue_count",
    "reviews": "review_count",
    "repositories": "repository_count",
    "actions": "action_count",
}

_REPO_CONTRIB_CACHE_TTL = 86400 * 30  # 30 days

# Per-(user, year) in-process locks so concurrent requests (double render,
# multiple tabs) never re-run the expensive GitHub aggregation in parallel.
_AGGREGATION_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}


def _level(count: int) -> int:
    if count <= 0:
        return 0
    if count <= 2:
        return 1
    if count <= 5:
        return 2
    if count <= 10:
        return 3
    return 4


class ContributionService:
    def __init__(
        self,
        *,
        db: AsyncSession,
        github: GitHubAPIClient,
        tokens: TokenService,
        audit: AuditService,
        redis: RedisClient,
    ) -> None:
        self._db = db
        self._github = github
        self._tokens = tokens
        self._audit = audit
        self._redis = redis

    @staticmethod
    def _window_bounds(year: int) -> tuple[date, date]:
        """Date range shown for a year.

        - Current year → the trailing 12 full calendar months ending today
          (slides forward as time passes, GitHub-profile style).
        - Past years → the full calendar year (which is exactly 12 months).
        """
        today = date.today()
        if year == today.year:
            end = today
            start = date(today.year, today.month, 1)
            for _ in range(11):
                if start.month == 1:
                    start = date(start.year - 1, 12, 1)
                else:
                    start = date(start.year, start.month - 1, 1)
        else:
            start = date(year, 1, 1)
            end = date(year, 12, 31)
        return start, end

    # -- Public -------------------------------------------------------- #
    async def get_year(
        self, user_id: uuid.UUID, year: int, *, refresh: bool = False
    ) -> dict[str, Any]:
        """Grid payload for a year: one entry per day with type breakdown."""
        if refresh:
            await self.refresh(user_id, year)
        else:
            await self.ensure_year(user_id, year)

        login = await self._tokens.github_login_for_user(user_id)
        rows = await self._rows_for_year(user_id, year)

        days = []
        total = 0
        max_count = 0
        for row in rows:
            count = row.count or 0
            total += count
            max_count = max(max_count, count)
            days.append(
                {
                    "date": row.date.isoformat(),
                    "count": count,
                    "level": _level(count),
                    "commits": row.commit_count or 0,
                    "pull_requests": row.pull_request_count or 0,
                    "issues": row.issue_count or 0,
                    "reviews": row.review_count or 0,
                    "repositories": row.repository_count or 0,
                    "actions": row.action_count or 0,
                }
            )

        await self._audit.record(
            AuditEventType.REPOSITORY_ACCESS,
            user_id=user_id,
            action="contribution.access.read",
            resource_type="contribution",
            resource_id=str(year),
        )
        return {
            "year": year,
            "connected": login is not None,
            "days": days,
            "total": total,
            "max": max_count,
            "breakdown": self._breakdown(rows),
        }

    async def get_streaks(self, user_id: uuid.UUID, year: int) -> dict[str, Any]:
        rows = await self._rows_for_year(user_id, year)
        counts = {row.date: (row.count or 0) for row in rows}
        if not counts:
            return {"current_streak": 0, "longest_streak": 0}

        longest = 0
        run = 0
        start, end = self._window_bounds(year)
        day = start
        while day <= end:
            if counts.get(day, 0) > 0:
                run += 1
                longest = max(longest, run)
            else:
                run = 0
            day += timedelta(days=1)

        current = 0
        day = end
        while day >= start and counts.get(day, 0) > 0:
            current += 1
            day -= timedelta(days=1)

        return {
            "current_streak": current,
            "longest_streak": longest,
            "current_streak_end": end.isoformat() if current else None,
        }

    async def get_statistics(self, user_id: uuid.UUID, year: int) -> dict[str, Any]:
        rows = await self._rows_for_year(user_id, year)
        start, end = self._window_bounds(year)
        elapsed = (end - start).days + 1

        total = sum(row.count or 0 for row in rows)
        days_contributed = sum(1 for row in rows if (row.count or 0) > 0)
        month_totals: dict[int, int] = {}
        weekday_totals: dict[int, int] = {}
        for row in rows:
            if (row.count or 0) > 0:
                month_totals[row.date.month] = month_totals.get(row.date.month, 0) + (
                    row.count or 0
                )
                weekday_totals[row.date.weekday()] = weekday_totals.get(row.date.weekday(), 0) + (
                    row.count or 0
                )

        most_active_month = (
            max(month_totals, key=lambda k: month_totals[k]) if month_totals else None
        )
        most_active_weekday = (
            max(weekday_totals, key=lambda k: weekday_totals[k]) if weekday_totals else None
        )

        await self._audit.record(
            AuditEventType.REPOSITORY_ACCESS,
            user_id=user_id,
            action="contribution.access.statistics",
            resource_type="contribution",
            resource_id=str(year),
        )
        return {
            "total": total,
            "days_contributed": days_contributed,
            "average_per_day": round(total / elapsed, 2) if elapsed else 0,
            "most_active_month": most_active_month,
            "most_active_month_contributions": month_totals.get(most_active_month, 0)
            if most_active_month
            else 0,
            "most_active_weekday": most_active_weekday,
            "most_active_weekday_contributions": weekday_totals.get(most_active_weekday, 0)
            if most_active_weekday
            else 0,
            "most_active_repository": await self._most_active_repository(
                user_id, self._label(year)
            ),
            "breakdown": self._breakdown(rows),
        }

    @staticmethod
    def _label(year: int) -> str:
        return "current" if year == date.today().year else str(year)

    async def refresh(self, user_id: uuid.UUID, year: int) -> bool:
        start, end = self._window_bounds(year)
        await self._db.execute(
            delete(Contribution).where(
                Contribution.user_id == user_id,
                Contribution.date >= start,
                Contribution.date <= end,
            )
        )
        await self._db.flush()
        return await self._aggregate(user_id, start, end, self._label(year))

    # -- Internal ------------------------------------------------------ #
    async def ensure_year(self, user_id: uuid.UUID, year: int) -> None:
        if not await self._has_year(user_id, year):
            start, end = self._window_bounds(year)
            await self._aggregate(user_id, start, end, self._label(year))

    async def _has_year(self, user_id: uuid.UUID, year: int) -> bool:
        start, end = self._window_bounds(year)
        row = await self._db.scalar(
            select(Contribution.id)
            .where(
                Contribution.user_id == user_id,
                Contribution.date >= start,
                Contribution.date <= end,
            )
            .limit(1)
        )
        return row is not None

    async def _rows_for_year(self, user_id: uuid.UUID, year: int) -> list[Contribution]:
        start, end = self._window_bounds(year)
        result = await self._db.scalars(
            select(Contribution)
            .where(
                Contribution.user_id == user_id,
                Contribution.date >= start,
                Contribution.date <= end,
            )
            .order_by(Contribution.date)
        )
        return list(result)

    async def _aggregate(self, user_id: uuid.UUID, start: date, end: date, label: str) -> bool:
        key = (str(user_id), label)
        lock = _AGGREGATION_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _AGGREGATION_LOCKS[key] = lock
        async with lock:
            return await self._aggregate_locked(user_id, start, end, label)

    async def _aggregate_locked(
        self, user_id: uuid.UUID, start: date, end: date, label: str
    ) -> bool:
        try:
            token = await self._tokens.access_token_for_user(user_id)
        except TokenInvalidError:
            return False
        login = await self._tokens.github_login_for_user(user_id)
        if not login:
            return False

        try:
            calendar = await self._github.get_contribution_calendar(token, login, start, end)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        totals = {day["date"]: int(day.get("count") or 0) for day in calendar.get("days", [])}
        typed, repo_contribs = await self._typed_days(token, login, start, end, label)

        existing = await self._db.scalars(
            select(Contribution).where(
                Contribution.user_id == user_id,
                Contribution.date >= start,
                Contribution.date <= end,
            )
        )
        by_date = {row.date: row for row in existing}

        day = start
        while day <= end:
            iso = day.isoformat()
            row = by_date.get(day)
            if row is None:
                row = Contribution(user_id=user_id, date=day)
                self._db.add(row)
                by_date[day] = row
            row.count = int(totals.get(iso, 0))
            for type_name, field in _FIELD_BY_TYPE.items():
                setattr(row, field, int((typed.get(type_name) or {}).get(iso, 0)))
            day += timedelta(days=1)

        await self._db.flush()
        if repo_contribs:
            try:
                await self._redis.set_json(
                    f"gh:contribrepo:{login}:{label}",
                    {
                        "repos": [
                            {"full_name": name, "count": count}
                            for name, count in sorted(
                                repo_contribs.items(), key=lambda kv: kv[1], reverse=True
                            )
                        ]
                    },
                    ttl=_REPO_CONTRIB_CACHE_TTL,
                )
            except Exception:  # noqa: BLE001 - cache is best-effort
                logger.warning("gh_contribrepo_cache_write_failed", login=login, label=label)
        return True

    async def _typed_days(
        self, token: str, login: str, start: date, end: date, label: str
    ) -> tuple[dict[str, dict[str, int]], dict[str, int]]:
        """Best-effort per-day per-type counts + per-repo commit counts.

        All GitHub fetches run concurrently (they are independent) so first-load
        latency is bounded by the slowest call rather than their sum. The repo
        list is fetched once and shared between repository-creation and action
        counts to avoid a second paginated list call.
        """

        async def safe(name: str, coro: Any) -> Any:
            try:
                return await coro
            except (GitHubClientError, TokenInvalidError):
                logger.warning("contribution_type_failed", type=name, label=label)
                return None

        commits_coro = self._github.get_commit_contribution_days(token, login, start, end)
        prs_coro = self._github.get_issue_contribution_days(token, login, start, end, pr_only=True)
        issues_coro = self._github.get_issue_contribution_days(token, login, start, end)
        reviews_coro = self._github.get_issue_contribution_days(
            token, login, start, end, reviewed=True
        )
        repos_coro = self._github.list_repositories(token)

        commits_raw, prs, issues, reviews, repos_raw = await asyncio.gather(
            safe("commits", commits_coro),
            safe("pull_requests", prs_coro),
            safe("issues", issues_coro),
            safe("reviews", reviews_coro),
            safe("repos", repos_coro),
        )

        commits, repo_contribs = {}, {}
        if isinstance(commits_raw, tuple):
            commits, repo_contribs = commits_raw
        commits = commits if isinstance(commits, dict) else {}
        repo_contribs = repo_contribs if isinstance(repo_contribs, dict) else {}

        repos_list = repos_raw if isinstance(repos_raw, list) else []
        repos_created = await self._github.get_repository_creation_days(
            token, login, start, end, repos=repos_list
        )
        actions = await safe(
            "actions",
            self._github.get_action_days(token, login, start, end, repos=repos_list),
        )

        return {
            "commits": commits,
            "pull_requests": prs or {},
            "issues": issues or {},
            "reviews": reviews or {},
            "repositories": repos_created,
            "actions": actions or {},
        }, repo_contribs

    async def _most_active_repository(
        self, user_id: uuid.UUID, label: str
    ) -> dict[str, Any] | None:
        login = await self._tokens.github_login_for_user(user_id)
        if not login:
            return None
        try:
            data = await self._redis.get_json(f"gh:contribrepo:{login}:{label}")
        except Exception:  # noqa: BLE001 - degrade to no repo
            data = None
        repos = (data or {}).get("repos") or []
        if not repos:
            return None
        top = repos[0]
        return {"full_name": top["full_name"], "contributions": top["count"]}

    @staticmethod
    def _breakdown(rows: list[Contribution]) -> dict[str, int]:
        breakdown = {name: 0 for name in _FIELD_BY_TYPE}
        for row in rows:
            for name, field in _FIELD_BY_TYPE.items():
                breakdown[name] += getattr(row, field) or 0
        return breakdown
