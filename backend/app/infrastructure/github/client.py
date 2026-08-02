"""Reusable async GitHub API client.

Features
--------
- OAuth-bearer authentication (token never leaves the backend)
- REST + GraphQL
- Link-header + cursor pagination
- Exponential backoff retries with full jitter
- Rate-limit awareness (X-RateLimit-* headers, secondary 429s, reset tracking)
- Conditional requests via ETag caching in Redis
- Typed responses (Pydantic)
- Error normalization → GitHubClientError hierarchy

Designed so the underlying transport can swap between OAuth App and GitHub App
authentication without callers changing.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import random
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, TypeVar, cast

import httpx
import orjson

from app.core.config import Settings
from app.core.logging import get_logger
from app.infrastructure.github.exceptions import (
    GitHubClientError,
    GitHubRateLimitError,
    GitHubUnavailableError,
    normalize_github_error,
)
from app.infrastructure.github.models import (
    GHBase,
    GHBranch,
    GHComment,
    GHCommit,
    GHDiscussion,
    GHEmail,
    GHIssue,
    GHLabels,
    GHMilestone,
    GHOrganization,
    GHPackage,
    GHPaged,
    GHPullRequest,
    GHRateLimit,
    GHRelease,
    GHRepository,
    GHTeam,
    GHUser,
    GHWorkflow,
    GHWorkflowRun,
)
from app.infrastructure.redis.client import RedisClient

logger = get_logger("github")

T = TypeVar("T", bound=GHBase)

_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
_TRANSPORT_RETRIES = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)
_MAX_PAGE_SIZE = 100
_DEFAULT_PER_PAGE = 30


class GitHubAPIClient:
    def __init__(self, settings: Settings, redis: RedisClient) -> None:
        self._settings = settings
        self._redis = redis
        self._base_url = settings.GITHUB_API_BASE_URL.rstrip("/")
        self._timeout = httpx.Timeout(settings.GH_HTTP_TIMEOUT_SECONDS)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": f"{settings.APP_NAME}/{settings.APP_VERSION}",
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------------ #
    # Core request
    # ------------------------------------------------------------------ #
    async def request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | list[Any] | None = None,
        etag: str | None = None,
        retries: int | None = None,
    ) -> httpx.Response:
        url = path if path.startswith(("http://", "https://")) else path
        headers = {"Authorization": f"Bearer {token}"}
        if etag:
            headers["If-None-Match"] = etag
        if json_body is not None:
            headers["Content-Type"] = "application/json"

        max_attempts = retries or self._settings.GH_RETRY_MAX_ATTEMPTS
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = await self._client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    content=orjson.dumps(json_body) if json_body is not None else None,
                )
            except _TRANSPORT_RETRIES as exc:
                if attempt >= max_attempts:
                    raise GitHubUnavailableError(
                        f"Transport error talking to GitHub: {exc}"
                    ) from exc
                await self._backoff(attempt)
                continue

            # Rate-limit bookkeeping (for observability + proactive checks)
            await self._record_rate_limit(resp.headers)

            if resp.status_code == 304:
                try:
                    cached = await self._redis.get_json(self._etag_key(url, token, params))
                    header_record = await self._redis.get_json(
                        self._etag_header_key(url, token, params)
                    )
                except Exception:  # noqa: BLE001 - Redis outage → fall through to upstream 304
                    cached = None
                    header_record = None
                if cached is not None:
                    headers = {}
                    if header_record and header_record.get("link"):
                        headers["Link"] = header_record["link"]
                    resp = httpx.Response(200, request=resp.request, json=cached, headers=headers)
                    return resp
                return resp

            if resp.status_code in _RETRYABLE_STATUS:
                reset_at = self._parse_reset(resp)
                if resp.status_code == 429 or (resp.status_code == 403 and reset_at):
                    # Secondary rate limit — obey Retry-After.
                    retry_after = self._parse_retry_after(resp)
                    if attempt >= max_attempts:
                        raise GitHubRateLimitError(
                            "GitHub rate limit exceeded",
                            reset_at=reset_at,
                            status_code=resp.status_code,
                        )
                    await asyncio.sleep(min(retry_after, self._settings.GH_MAX_RETRY_WAIT_SECONDS))
                    continue
                if attempt >= max_attempts:
                    body = self._safe_json(resp)
                    raise normalize_github_error(resp.status_code, body)
                await self._backoff(attempt)
                continue

            if resp.status_code >= 400:
                body = self._safe_json(resp)
                if resp.status_code == 403 and self._is_rate_limited(resp.headers):
                    raise GitHubRateLimitError(
                        "GitHub rate limit exceeded",
                        reset_at=self._parse_reset(resp),
                        status_code=403,
                        body=body,
                    )
                raise normalize_github_error(resp.status_code, body)

            # Success — cache body + etag for GETs.
            if method.upper() == "GET" and resp.status_code == 200:
                etag_value = resp.headers.get("ETag")
                if etag_value:
                    try:
                        await self._redis.set_json(
                            self._etag_key(url, token, params),
                            resp.json(),
                            ttl=self._settings.GH_CACHE_TTL_SECONDS,
                        )
                        await self._redis.set_json(
                            self._etag_header_key(url, token, params),
                            {
                                "etag": etag_value,
                                "link": resp.headers.get("Link") or None,
                            },
                            ttl=self._settings.GH_CACHE_TTL_SECONDS,
                        )
                    except Exception:  # pragma: no cover
                        logger.warning("gh_cache_write_failed", url=url)
            return resp

    async def _backoff(self, attempt: int) -> None:
        base = self._settings.GH_RETRY_BASE_BACKOFF
        cap = self._settings.GH_MAX_RETRY_WAIT_SECONDS
        delay = min(base * (2 ** (attempt - 1)), cap)
        jittered = delay / 2 + random.uniform(0, delay / 2)
        await asyncio.sleep(jittered)

    # ------------------------------------------------------------------ #
    # Rate-limit utilities
    # ------------------------------------------------------------------ #
    @staticmethod
    def _parse_reset(resp: httpx.Response) -> int | None:
        raw = resp.headers.get("X-RateLimit-Reset")
        if raw and raw.isdigit():
            return int(raw)
        return None

    @staticmethod
    def _parse_retry_after(resp: httpx.Response) -> float:
        raw = resp.headers.get("Retry-After")
        if raw and raw.isdigit():
            return float(raw)
        return 1.0

    @staticmethod
    def _safe_json(resp: httpx.Response) -> dict[str, Any]:
        """Parse a response body as a dict, tolerating non-JSON error bodies."""
        try:
            data = resp.json()
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {"message": str(data)}

    @staticmethod
    def _is_rate_limited(headers: Mapping[str, str]) -> bool:
        remaining = headers.get("X-RateLimit-Remaining")
        return remaining is not None and remaining.isdigit() and int(remaining) == 0

    async def _record_rate_limit(self, headers: Mapping[str, str]) -> None:
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        if not remaining or not remaining.isdigit():
            return
        with contextlib.suppress(Exception):
            await self._redis.set_json(
                "gh:ratelimit:core", {"remaining": int(remaining), "reset": reset}, ttl=3600
            )

    async def get_rate_limit(self, token: str) -> GHRateLimit:
        resp = await self.request("GET", "/rate_limit", token)
        return GHRateLimit.model_validate(resp.json())

    # ------------------------------------------------------------------ #
    # ETag helpers
    # ------------------------------------------------------------------ #
    def _etag_key(self, url: str, token: str, params: dict[str, Any] | None) -> str:
        digest = hashlib.sha256(f"{url}:{params or {}}".encode()).hexdigest()
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:16]
        return f"gh:cache:{token_hash}:{digest}"

    def _etag_header_key(self, url: str, token: str, params: dict[str, Any] | None) -> str:
        return f"{self._etag_key(url, token, params)}:hdr"

    async def _fetch_with_etag(
        self, method: str, path: str, token: str, *, params: dict[str, Any] | None = None
    ) -> httpx.Response:
        etag = None
        try:
            header = await self._redis.get_json(self._etag_header_key(path, token, params))
        except Exception:  # noqa: BLE001 - Redis outage degrades to a plain request
            header = None
        if header:
            etag = header.get("etag")
        return await self.request(method, path, token, params=params, etag=etag)

    # ------------------------------------------------------------------ #
    # Pagination
    # ------------------------------------------------------------------ #
    async def paginate(
        self,
        path: str,
        token: str,
        *,
        model: type[T],
        params: dict[str, Any] | None = None,
        max_pages: int = 100,
    ) -> list[T]:
        items: list[T] = []
        page_params = {**(params or {}), "per_page": _DEFAULT_PER_PAGE}
        page = 1
        while page <= max_pages:
            resp = await self._fetch_with_etag("GET", path, token, params=page_params)
            if resp.status_code == 200:
                raw = resp.json()
                items.extend(model.model_validate(item) for item in raw)
            link = resp.headers.get("Link", "")
            nxt = self._extract_next_link(link)
            if not nxt or page_params.get("page") and not nxt:
                break
            page_params["page"] = page_params.get("page", 1) + 1
            page += 1
        return items

    @staticmethod
    def _extract_next_link(link_header: str) -> str | None:
        for part in link_header.split(","):
            section = part.split(";")
            if len(section) < 2:
                continue
            if any('rel="next"' in s or "rel='next'" in s for s in section[1:]):
                url = section[0].strip().strip("<>")
                return url
        return None

    @staticmethod
    def _extract_last_page(link_header: str) -> int | None:
        """Return the page number of the `rel="last"` link, if present."""
        for part in link_header.split(","):
            section = part.split(";")
            if len(section) < 2:
                continue
            if any('rel="last"' in s or "rel='last'" in s for s in section[1:]):
                url = section[0].strip().strip("<>")
                from urllib.parse import parse_qs, urlparse

                qs = parse_qs(urlparse(url).query)
                page = qs.get("page", ["1"])[0]
                return int(page) if page.isdigit() else None
        return None

    # ------------------------------------------------------------------ #
    # GraphQL
    # ------------------------------------------------------------------ #
    async def graphql(
        self, token: str, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        resp = await self.request("POST", "/graphql", token, json_body=body)
        payload: dict[str, Any] = resp.json()
        if "errors" in payload:
            raise GitHubClientError("GraphQL error", body={"errors": payload["errors"]})
        return cast(dict[str, Any], payload.get("data", {}))

    # ------------------------------------------------------------------ #
    # Typed REST helpers
    # ------------------------------------------------------------------ #
    async def get_user(self, token: str) -> GHUser:
        resp = await self._fetch_with_etag("GET", "/user", token)
        return GHUser.model_validate(resp.json())

    async def get_user_emails(self, token: str) -> list[GHEmail]:
        resp = await self._fetch_with_etag("GET", "/user/emails", token)
        return [GHEmail.model_validate(item) for item in resp.json()]

    async def get_primary_email(self, token: str) -> str | None:
        emails = await self.get_user_emails(token)
        verified = [e for e in emails if e.verified and e.primary]
        if verified:
            return verified[0].email
        primary = [e for e in emails if e.primary]
        return primary[0].email if primary else None

    async def list_organizations(self, token: str) -> list[GHOrganization]:
        return await self.paginate(
            "/user/orgs", token, model=GHOrganization, params={"per_page": 100}
        )

    async def list_repositories(
        self, token: str, *, visibility: str | None = None, affiliation: str | None = None
    ) -> list[GHRepository]:
        params: dict[str, Any] = {"per_page": 100}
        if visibility:
            params["visibility"] = visibility
        if affiliation:
            params["affiliation"] = affiliation
        return await self.paginate("/user/repos", token, model=GHRepository, params=params)

    async def list_repositories_page(
        self,
        token: str,
        *,
        page: int = 1,
        per_page: int = 30,
        visibility: str | None = None,
        affiliation: str | None = None,
        q: str | None = None,
    ) -> GHPaged:
        """Fetch a single page of the user's repositories with pagination meta.

        GitHub does not return an exact total for this endpoint, so the total is
        derived from the `rel="last"` link (exact when the last page is partial).
        When `q` is provided, delegates to the search API (`user:` scoped).
        """
        params: dict[str, Any] = {"page": page, "per_page": per_page}
        if visibility:
            params["visibility"] = visibility
        if affiliation:
            params["affiliation"] = affiliation
        if q:
            resp = await self._fetch_with_etag(
                "GET", "/search/repositories", token, params={**params, "q": q}
            )
            raw = resp.json()
            items = [GHRepository.model_validate(item) for item in raw.get("items", [])]
            return GHPaged(
                items=items,
                total_count=int(raw.get("total_count") or 0),
            )
        resp = await self._fetch_with_etag("GET", "/user/repos", token, params=params)
        items = [GHRepository.model_validate(item) for item in resp.json()]
        link = resp.headers.get("Link", "")
        nxt = self._extract_next_link(link)
        last_page = self._extract_last_page(link)
        total_count: int | None = None
        if last_page is not None:
            if page >= last_page:
                total_count = (last_page - 1) * per_page + len(items)
            else:
                total_count = last_page * per_page
        return GHPaged(items=items, next_page=nxt, total_count=total_count)

    async def get_commit_count_for_user(
        self, token: str, owner: str, repo: str, author: str
    ) -> int:
        """Count commits authored by a user in a repository.

        Uses GitHub's classic trick: request per_page=1 and read the page number
        from the `rel="last"` link. Results are cached in Redis so the expensive
        per-repo lookups don't hit GitHub on every page load.
        """
        cache_key = f"gh:commitcount:{owner}/{repo}:{author}"
        try:
            cached = await self._redis.get_json(cache_key)
        except Exception:  # noqa: BLE001
            cached = None
        if cached is not None:
            try:
                return int(cached)
            except (TypeError, ValueError):
                await self._redis.delete(cache_key)
        resp = await self.request(
            "GET", f"/repos/{owner}/{repo}/commits", token, params={"author": author, "per_page": 1}
        )
        last = self._extract_last_page(resp.headers.get("Link", ""))
        count = last if last is not None else len(resp.json())
        try:
            await self._redis.set_json(
                cache_key, count, ttl=self._settings.GH_CACHE_TTL_SECONDS * 15
            )
        except Exception:  # noqa: BLE001
            logger.warning("gh_commit_count_cache_write_failed", owner=owner, repo=repo)
        return count

    async def get_contributions_summary(self, token: str, login: str) -> dict[str, int]:
        """Yearly contribution totals (GitHub profile style) via GraphQL."""
        query = """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              totalPullRequestContributions
              totalIssueContributions
              totalPullRequestReviewContributions
              contributionCalendar {
                totalContributions
              }
            }
          }
        }
        """
        now = datetime.now(UTC)
        to = now.isoformat()
        _from = (now - timedelta(days=365)).isoformat()
        cache_key = f"gh:contrib:{login}:{now.strftime('%Y')}"
        try:
            cached = await self._redis.get_json(cache_key)
        except Exception:  # noqa: BLE001
            cached = None
        if cached is not None:
            return cast(dict[str, int], cached)
        data = await self.graphql(token, query, {"login": login, "from": _from, "to": to})
        coll = ((data or {}).get("user") or {}).get("contributionsCollection") or {}
        calendar = coll.get("contributionCalendar") or {}
        result = {
            "commits": int(coll.get("totalCommitContributions") or 0),
            "pull_requests": int(coll.get("totalPullRequestContributions") or 0),
            "issues": int(coll.get("totalIssueContributions") or 0),
            "reviews": int(coll.get("totalPullRequestReviewContributions") or 0),
            "total": int(calendar.get("totalContributions") or 0),
        }
        try:
            await self._redis.set_json(
                cache_key, result, ttl=self._settings.GH_CACHE_TTL_SECONDS * 15
            )
        except Exception:  # noqa: BLE001
            logger.warning("gh_contrib_cache_write_failed", login=login)
        return result

    # ------------------------------------------------------------------ #
    # Contribution calendar / heatmap
    # ------------------------------------------------------------------ #
    _CONTRIBUTION_CALENDAR_QUERY = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          totalPullRequestReviewContributions
          totalRepositoryContributions
          restrictedContributionsCount
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                contributionCount
                date
              }
            }
          }
        }
      }
    }
    """

    async def get_contribution_calendar(
        self, token: str, login: str, from_date: date, to_date: date
    ) -> dict[str, Any]:
        """GitHub's exact per-day contribution calendar for a date range.

        Uses the GraphQL `contributionsCollection` (the same source as the
        GitHub profile heatmap) so the grid matches GitHub day-for-day. Results
        are cached in Redis (per login + date range).
        """
        now = datetime.now(UTC)
        if to_date > now.date():
            to_date = now.date()
        start_dt = datetime(from_date.year, from_date.month, from_date.day, tzinfo=UTC)
        end_dt = datetime(to_date.year, to_date.month, to_date.day, 23, 59, 59, tzinfo=UTC)
        cache_key = f"gh:calendar:{login}:{from_date.isoformat()}:{to_date.isoformat()}"
        try:
            cached = await self._redis.get_json(cache_key)
        except Exception:  # noqa: BLE001 - Redis outage → live fetch
            cached = None
        if cached is not None:
            return cast(dict[str, Any], cached)

        data = await self.graphql(
            token,
            self._CONTRIBUTION_CALENDAR_QUERY,
            {"login": login, "from": start_dt.isoformat(), "to": end_dt.isoformat()},
        )
        coll = ((data or {}).get("user") or {}).get("contributionsCollection") or {}
        calendar = coll.get("contributionCalendar") or {}
        days = [
            {"date": day.get("date"), "count": int(day.get("contributionCount") or 0)}
            for week in calendar.get("weeks", [])
            for day in week.get("contributionDays", [])
        ]
        result: dict[str, Any] = {
            "days": days,
            "total": int(calendar.get("totalContributions") or 0),
            "breakdown": {
                "commits": int(coll.get("totalCommitContributions") or 0),
                "pull_requests": int(coll.get("totalPullRequestContributions") or 0),
                "issues": int(coll.get("totalIssueContributions") or 0),
                "reviews": int(coll.get("totalPullRequestReviewContributions") or 0),
                "repositories": int(coll.get("totalRepositoryContributions") or 0),
                "actions": 0,
            },
        }
        try:
            await self._redis.set_json(
                cache_key, result, ttl=self._settings.GH_CACHE_TTL_SECONDS * 60
            )
        except Exception:  # noqa: BLE001
            logger.warning("gh_calendar_cache_write_failed", login=login, year=to_date.year)
        return result

    async def _search_all(
        self, token: str, path: str, params: dict[str, Any], *, max_pages: int = 10
    ) -> list[dict[str, Any]]:
        """Bounded REST search pagination (search API rate limits are strict)."""
        items: list[dict[str, Any]] = []
        base = {**params, "per_page": 100}
        for page in range(1, max_pages + 1):
            resp = await self._fetch_with_etag("GET", path, token, params={**base, "page": page})
            if resp.status_code != 200:
                break
            raw = resp.json()
            items.extend(raw.get("items", []))
            total = raw.get("total_count", 0)
            if total == 0 or len(items) >= total:
                break
        return items

    @staticmethod
    def _date_prefix(value: Any) -> str:
        """Extract `YYYY-MM-DD` from a GitHub timestamp string."""
        raw = str(value or "")
        return raw[:10] if len(raw) >= 10 else ""

    async def get_commit_contribution_days(
        self, token: str, login: str, from_date: date, to_date: date
    ) -> tuple[dict[str, int], dict[str, int]]:
        """Per-day commit counts + per-repo commit counts for a date range.

        Uses REST commit search (bounded); `(days, repo_contribs)` where keys
        are `YYYY-MM-DD` / `owner/name`.
        """
        q = f"author:{login} committer-date:{from_date}..{to_date}"
        items = await self._search_all(token, "/search/commits", {"q": q}, max_pages=5)
        days: dict[str, int] = {}
        repos: dict[str, int] = {}
        for item in items:
            repo = (item.get("repository") or {}).get("full_name") or "unknown"
            repos[repo] = repos.get(repo, 0) + 1
            d = self._date_prefix((item.get("commit") or {}).get("author", {}).get("date"))
            if d:
                days[d] = days.get(d, 0) + 1
        return days, repos

    async def get_issue_contribution_days(
        self,
        token: str,
        login: str,
        from_date: date,
        to_date: date,
        *,
        pr_only: bool = False,
        reviewed: bool = False,
    ) -> dict[str, int]:
        """Per-day PR / issue / review counts via issue search.

        `pr_only=True` → opened pull requests; `reviewed=True` → PRs the user
        reviewed (approximate: `updated` within the range).
        """
        if reviewed:
            q = f"reviewed-by:{login} type:pr updated:{from_date}..{to_date}"
            field = "updated_at"
        elif pr_only:
            q = f"author:{login} type:pr created:{from_date}..{to_date}"
            field = "created_at"
        else:
            q = f"author:{login} type:issue created:{from_date}..{to_date}"
            field = "created_at"
        items = await self._search_all(token, "/search/issues", {"q": q}, max_pages=5)
        days: dict[str, int] = {}
        for item in items:
            d = self._date_prefix(item.get(field))
            if d:
                days[d] = days.get(d, 0) + 1
        return days

    async def get_repository_creation_days(
        self,
        token: str,
        login: str,
        from_date: date,
        to_date: date,
        *,
        repos: Sequence[GHRepository] | None = None,
    ) -> dict[str, int]:
        """Per-day repository-creation counts within a date range."""
        if repos is None:
            repos = await self.list_repositories(token)
        lo, hi = from_date.isoformat(), to_date.isoformat()
        days: dict[str, int] = {}
        for repo in repos:
            d = self._date_prefix(repo.created_at)
            if d and lo <= d <= hi:
                days[d] = days.get(d, 0) + 1
        return days

    async def get_action_days(
        self,
        token: str,
        login: str,
        from_date: date,
        to_date: date,
        *,
        repos: Sequence[GHRepository] | None = None,
        max_repos: int = 5,
    ) -> dict[str, int]:
        """Per-day workflow-run counts (bounded to the first N repos)."""
        if repos is None:
            repos = await self.list_repositories(token)
        days: dict[str, int] = {}
        for repo in repos[:max_repos]:
            owner = (repo.full_name or repo.name).split("/")[0]
            try:
                resp = await self._fetch_with_etag(
                    "GET",
                    f"/repos/{owner}/{repo.name}/actions/runs",
                    token,
                    params={"created": f"{from_date}..{to_date}", "per_page": 100},
                )
            except GitHubClientError:
                continue
            if resp.status_code != 200:
                continue
            for run in resp.json().get("workflow_runs", []):
                d = self._date_prefix(run.get("created_at"))
                if d:
                    days[d] = days.get(d, 0) + 1
        return days

    async def get_repository(self, token: str, owner: str, repo: str) -> GHRepository:
        resp = await self._fetch_with_etag("GET", f"/repos/{owner}/{repo}", token)
        return GHRepository.model_validate(resp.json())

    async def create_repository(self, token: str, *, name: str, **kwargs: Any) -> GHRepository:
        resp = await self.request("POST", "/user/repos", token, json_body={"name": name, **kwargs})
        return GHRepository.model_validate(resp.json())

    async def delete_repository(self, token: str, owner: str, repo: str) -> None:
        await self.request("DELETE", f"/repos/{owner}/{repo}", token)

    async def fork_repository(
        self, token: str, owner: str, repo: str, *, organization: str | None = None
    ) -> GHRepository:
        body = {"organization": organization} if organization else None
        resp = await self.request("POST", f"/repos/{owner}/{repo}/forks", token, json_body=body)
        return GHRepository.model_validate(resp.json())

    async def list_branches(self, token: str, owner: str, repo: str) -> list[GHBranch]:
        return await self.paginate(f"/repos/{owner}/{repo}/branches", token, model=GHBranch)

    async def get_branch(self, token: str, owner: str, repo: str, branch: str) -> GHBranch:
        resp = await self._fetch_with_etag("GET", f"/repos/{owner}/{repo}/branches/{branch}", token)
        return GHBranch.model_validate(resp.json())

    async def create_branch(
        self, token: str, owner: str, repo: str, *, name: str, from_sha: str
    ) -> None:
        body = {"ref": f"refs/heads/{name}", "sha": from_sha}
        await self.request("POST", f"/repos/{owner}/{repo}/git/refs", token, json_body=body)

    async def list_commits(
        self, token: str, owner: str, repo: str, *, sha: str | None = None
    ) -> list[GHCommit]:
        params = {"sha": sha} if sha else None
        return await self.paginate(
            f"/repos/{owner}/{repo}/commits", token, model=GHCommit, params=params
        )

    async def get_commit(self, token: str, owner: str, repo: str, ref: str) -> GHCommit:
        resp = await self._fetch_with_etag("GET", f"/repos/{owner}/{repo}/commits/{ref}", token)
        return GHCommit.model_validate(resp.json())

    async def create_commit(
        self, token: str, owner: str, repo: str, *, message: str, tree: str, parents: list[str]
    ) -> GHCommit:
        resp = await self.request(
            "POST",
            f"/repos/{owner}/{repo}/git/commits",
            token,
            json_body={"message": message, "tree": tree, "parents": parents},
        )
        return GHCommit.model_validate(resp.json())

    async def merge_branch(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        base: str,
        head: str,
        commit_message: str | None = None,
    ) -> GHCommit:
        body: dict[str, Any] = {"base": base, "head": head}
        if commit_message:
            body["commit_message"] = commit_message
        resp = await self.request("POST", f"/repos/{owner}/{repo}/merges", token, json_body=body)
        return GHCommit.model_validate(resp.json())

    # --- Pull requests ---
    async def list_pull_requests(
        self, token: str, owner: str, repo: str, *, state: str = "open"
    ) -> list[GHPullRequest]:
        return await self.paginate(
            f"/repos/{owner}/{repo}/pulls",
            token,
            model=GHPullRequest,
            params={"state": state, "per_page": 100},
        )

    async def get_pull_request(
        self, token: str, owner: str, repo: str, number: int
    ) -> GHPullRequest:
        resp = await self._fetch_with_etag("GET", f"/repos/{owner}/{repo}/pulls/{number}", token)
        return GHPullRequest.model_validate(resp.json())

    async def create_pull_request(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
    ) -> GHPullRequest:
        payload: dict[str, Any] = {"title": title, "head": head, "base": base}
        if body:
            payload["body"] = body
        resp = await self.request("POST", f"/repos/{owner}/{repo}/pulls", token, json_body=payload)
        return GHPullRequest.model_validate(resp.json())

    async def merge_pull_request(
        self, token: str, owner: str, repo: str, number: int, *, merge_method: str = "merge"
    ) -> GHPullRequest:
        resp = await self.request(
            "PUT",
            f"/repos/{owner}/{repo}/pulls/{number}/merge",
            token,
            json_body={"merge_method": merge_method},
        )
        return GHPullRequest.model_validate(resp.json())

    async def request_reviewers(
        self, token: str, owner: str, repo: str, number: int, *, reviewers: list[str]
    ) -> None:
        await self.request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{number}/requested_reviewers",
            token,
            json_body={"reviewers": reviewers},
        )

    async def submit_review(
        self, token: str, owner: str, repo: str, number: int, *, body: str, event: str
    ) -> dict[str, Any]:
        resp = await self.request(
            "POST",
            f"/repos/{owner}/{repo}/pulls/{number}/reviews",
            token,
            json_body={"body": body, "event": event},
        )
        return cast(dict[str, Any], resp.json())

    # --- Issues ---
    async def list_issues(
        self, token: str, owner: str, repo: str, *, state: str = "open"
    ) -> list[GHIssue]:
        return await self.paginate(
            f"/repos/{owner}/{repo}/issues",
            token,
            model=GHIssue,
            params={"state": state, "per_page": 100},
        )

    async def list_assigned_issues(
        self, token: str, *, state: str = "open", per_page: int = 100
    ) -> list[GHIssue]:
        """Issues assigned to the authenticated user across all repositories."""
        return await self.paginate(
            "/issues",
            token,
            model=GHIssue,
            params={"filter": "assigned", "state": state, "per_page": per_page},
        )

    async def get_issue(self, token: str, owner: str, repo: str, number: int) -> GHIssue:
        resp = await self._fetch_with_etag("GET", f"/repos/{owner}/{repo}/issues/{number}", token)
        return GHIssue.model_validate(resp.json())

    async def create_issue(
        self, token: str, owner: str, repo: str, *, title: str, body: str | None = None
    ) -> GHIssue:
        payload: dict[str, Any] = {"title": title}
        if body:
            payload["body"] = body
        resp = await self.request("POST", f"/repos/{owner}/{repo}/issues", token, json_body=payload)
        return GHIssue.model_validate(resp.json())

    async def update_issue(
        self, token: str, owner: str, repo: str, number: int, **fields: Any
    ) -> GHIssue:
        resp = await self.request(
            "PATCH", f"/repos/{owner}/{repo}/issues/{number}", token, json_body=fields
        )
        return GHIssue.model_validate(resp.json())

    async def close_issue(self, token: str, owner: str, repo: str, number: int) -> GHIssue:
        return await self.update_issue(token, owner, repo, number, state="closed")

    async def comment_on_issue(
        self, token: str, owner: str, repo: str, number: int, *, body: str
    ) -> GHComment:
        resp = await self.request(
            "POST",
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            token,
            json_body={"body": body},
        )
        return GHComment.model_validate(resp.json())

    # --- Releases / labels / milestones ---
    async def list_releases(self, token: str, owner: str, repo: str) -> list[GHRelease]:
        return await self.paginate(f"/repos/{owner}/{repo}/releases", token, model=GHRelease)

    async def create_release(
        self, token: str, owner: str, repo: str, *, tag_name: str, **kwargs: Any
    ) -> GHRelease:
        resp = await self.request(
            "POST",
            f"/repos/{owner}/{repo}/releases",
            token,
            json_body={"tag_name": tag_name, **kwargs},
        )
        return GHRelease.model_validate(resp.json())

    async def list_labels(self, token: str, owner: str, repo: str) -> list[GHLabels]:
        return await self.paginate(f"/repos/{owner}/{repo}/labels", token, model=GHLabels)

    async def create_label(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        name: str,
        color: str,
        description: str | None = None,
    ) -> GHLabels:
        body: dict[str, Any] = {"name": name, "color": color}
        if description:
            body["description"] = description
        resp = await self.request("POST", f"/repos/{owner}/{repo}/labels", token, json_body=body)
        return GHLabels.model_validate(resp.json())

    async def list_milestones(self, token: str, owner: str, repo: str) -> list[GHMilestone]:
        return await self.paginate(f"/repos/{owner}/{repo}/milestones", token, model=GHMilestone)

    async def create_milestone(
        self, token: str, owner: str, repo: str, *, title: str, due_on: str | None = None
    ) -> GHMilestone:
        body: dict[str, Any] = {"title": title}
        if due_on:
            body["due_on"] = due_on
        resp = await self.request(
            "POST", f"/repos/{owner}/{repo}/milestones", token, json_body=body
        )
        return GHMilestone.model_validate(resp.json())

    # --- Actions / workflows ---
    async def list_workflows(self, token: str, owner: str, repo: str) -> list[GHWorkflow]:
        resp = await self._fetch_with_etag("GET", f"/repos/{owner}/{repo}/actions/workflows", token)
        return [GHWorkflow.model_validate(item) for item in resp.json().get("workflows", [])]

    async def dispatch_workflow(
        self,
        token: str,
        owner: str,
        repo: str,
        *,
        workflow_id: str,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> None:
        body: dict[str, Any] = {"ref": ref}
        if inputs:
            body["inputs"] = inputs
        await self.request(
            "POST",
            f"/repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches",
            token,
            json_body=body,
        )

    async def list_workflow_runs(self, token: str, owner: str, repo: str) -> list[GHWorkflowRun]:
        resp = await self._fetch_with_etag("GET", f"/repos/{owner}/{repo}/actions/runs", token)
        return [GHWorkflowRun.model_validate(item) for item in resp.json().get("workflow_runs", [])]

    # --- Teams / collaborators / packages / discussions ---
    async def list_teams(self, token: str, owner: str, repo: str) -> list[GHTeam]:
        return await self.paginate(f"/repos/{owner}/{repo}/teams", token, model=GHTeam)

    async def list_collaborators(self, token: str, owner: str, repo: str) -> list[GHUser]:
        return await self.paginate(f"/repos/{owner}/{repo}/collaborators", token, model=GHUser)

    async def list_packages(self, token: str, owner: str, repo: str) -> list[GHPackage]:
        return await self.paginate(f"/orgs/{owner}/packages", token, model=GHPackage)

    # --- GraphQL convenience: discussions ---
    _DISCUSSIONS_QUERY = """
    query($owner: String!, $repo: String!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        discussions(first: 25, after: $cursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id number title body
            author { login }
            category { name }
            createdAt updatedAt
          }
        }
      }
    }
    """

    async def list_discussions(self, token: str, owner: str, repo: str) -> list[GHDiscussion]:
        discussions: list[GHDiscussion] = []
        cursor: str | None = None
        for _ in range(50):
            data = await self.graphql(
                token, self._DISCUSSIONS_QUERY, {"owner": owner, "repo": repo, "cursor": cursor}
            )
            repo_data = (data or {}).get("repository")
            if not repo_data:
                break
            disc = repo_data.get("discussions", {})
            discussions.extend(GHDiscussion.model_validate(n) for n in disc.get("nodes", []))
            if not disc.get("pageInfo", {}).get("hasNextPage"):
                break
            cursor = disc.get("pageInfo", {}).get("endCursor")
        return discussions


__all__ = [
    "GitHubAPIClient",
    "GitHubClientError",
    "GitHubRateLimitError",
    "GitHubUnavailableError",
    "normalize_github_error",
]
