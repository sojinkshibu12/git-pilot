"""Shared test fixtures.

- In-memory SQLite (async) via the `Database` container
- Fake in-process Redis (dict-backed) so tests run without a Redis server
- Fake GitHub API client (recorded responses) so tests run without network
- A TestClient against the real `make_app()` application
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# `get_settings()` (lru_cached) reads from the environment, and several app
# modules call it lazily. Provide the required secrets so those calls work
# regardless of the ambient environment (CI only sets DATABASE_URL/REDIS_URL).
os.environ.setdefault("APP_ENV", "testing")
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")
os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "a" * 64)
os.environ.setdefault("GITHUB_CLIENT_ID", "test-client-id")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault(
    "GITHUB_REDIRECT_URI",
    "http://testserver/api/v1/auth/oauth/github/callback",
)
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://fake")

from app.core.config import Settings, get_settings  # noqa: E402


def _test_settings() -> Settings:
    return Settings(
        APP_ENV="testing",
        SECRET_KEY="test-secret-key-0123456789abcdef0123456789abcdef",
        TOKEN_ENCRYPTION_KEY="a" * 64,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://fake",
        GITHUB_CLIENT_ID="test-client-id",
        GITHUB_CLIENT_SECRET="test-client-secret",
        GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
        GITHUB_API_BASE_URL="https://api.github.com",
        GITHUB_WEB_BASE_URL="https://github.com",
        CORS_ORIGINS=["http://localhost:3000"],
    )


class FakeRedis:
    """Minimal dict-backed Redis substitute (no expiry enforcement in tests)."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._ttl: dict[str, int] = {}
        self.client = self

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None

    async def get(self, key: str) -> str | None:
        return self._data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._data[key] = value
        if ex:
            self._ttl[key] = ex

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._ttl.pop(key, None)

    async def expire(self, key: str, seconds: int) -> None:
        self._ttl[key] = seconds

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, -1)

    async def incr(self, key: str, ttl: int | None = None) -> int:
        val = int(self._data.get(key, 0)) + 1
        self._data[key] = str(val)
        if ttl and val == 1:
            self._ttl[key] = ttl
        return val

    async def set_json(self, key: str, value, ttl: int | None = None) -> None:
        import orjson

        self._data[key] = orjson.dumps(value).decode()
        if ttl:
            self._ttl[key] = ttl

    async def get_json(self, key: str):
        import orjson

        raw = self._data.get(key)
        if raw is None:
            return None
        try:
            return orjson.loads(raw)
        except orjson.JSONDecodeError:
            self._data.pop(key, None)
            self._ttl.pop(key, None)
            return None

    async def delete_pattern(self, pattern: str) -> None:
        import fnmatch

        for key in [k for k in self._data if fnmatch.fnmatch(k, pattern)]:
            self._data.pop(key, None)
            self._ttl.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def smembers(self, key: str) -> set[str]:
        raw = self._data.get(key)
        return set(raw.split(",")) if raw else set()

    async def sadd(self, key: str, *values: str) -> None:
        existing = await self.smembers(key)
        existing.update(values)
        self._data[key] = ",".join(existing)

    async def srem(self, key: str, *values: str) -> None:
        existing = await self.smembers(key)
        for v in values:
            existing.discard(v)
        self._data[key] = ",".join(existing) if existing else ""


class FakeGitHubClient:
    """Stubbed GitHub client with scriptable responses."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.users: dict[int, dict] = {}
        self.emails: list[dict] = []
        self.orgs: list[dict] = []
        self.repos: list[dict] = []
        self.calls: list[tuple[str, str]] = []

    async def get_user(self, token: str) -> object:
        self.calls.append(("GET", "/user"))
        gh = self.users.get(_tok_id(token), {})
        if not gh and self.users:
            # OAuth flows use a scripted access token; fall back to the single
            # registered user for this test.
            gh = next(iter(self.users.values()))
        from app.infrastructure.github.models import GHUser

        return GHUser.model_validate(gh)

    async def get_user_emails(self, token: str) -> list:
        from app.infrastructure.github.models import GHEmail

        return [GHEmail.model_validate(e) for e in self.emails]

    async def get_primary_email(self, token: str) -> str | None:
        for e in self.emails:
            if e["primary"] and e["verified"]:
                return e["email"]
        for e in self.emails:
            if e["primary"]:
                return e["email"]
        return None

    async def list_organizations(self, token: str) -> list:
        from app.infrastructure.github.models import GHOrganization

        return [GHOrganization.model_validate(o) for o in self.orgs]

    async def list_repositories(self, token: str) -> list:
        from app.infrastructure.github.models import GHRepository

        return [GHRepository.model_validate(r) for r in self.repos]

    async def list_repositories_page(
        self, token: str, *, page: int = 1, per_page: int = 30, **kwargs
    ) -> object:
        from app.infrastructure.github.models import GHPaged, GHRepository

        start = (page - 1) * per_page
        items = [GHRepository.model_validate(r) for r in self.repos[start : start + per_page]]
        total = len(self.repos)
        return GHPaged(
            items=items,
            next_page=None,
            total_count=total,
        )

    async def get_commit_count_for_user(
        self, token: str, owner: str, repo: str, author: str
    ) -> int:
        return 0

    async def get_contributions_summary(self, token: str, login: str) -> dict:
        return {"commits": 0, "pull_requests": 0, "issues": 0, "reviews": 0, "total": 0}

    async def get_contribution_calendar(self, token: str, login: str, from_date, to_date) -> dict:
        return {
            "days": [],
            "total": 0,
            "breakdown": {
                "commits": 0,
                "pull_requests": 0,
                "issues": 0,
                "reviews": 0,
                "repositories": 0,
                "actions": 0,
            },
        }

    async def get_commit_contribution_days(
        self, token: str, login: str, from_date, to_date
    ) -> tuple[dict, dict]:
        return {}, {}

    async def get_issue_contribution_days(
        self, token: str, login: str, from_date, to_date, **kwargs
    ) -> dict:
        return {}

    async def get_repository_creation_days(
        self, token: str, login: str, from_date, to_date, **kwargs
    ) -> dict:
        return {}

    async def get_action_days(self, token: str, login: str, from_date, to_date, **kwargs) -> dict:
        return {}

    async def graphql(self, token: str, query: str, variables: dict | None = None) -> dict:
        return {}

    async def get_repository(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHRepository

        return GHRepository.model_validate(
            {
                "id": 1,
                "full_name": f"{owner}/{repo}",
                "name": repo,
                "html_url": "",
                "owner": {"id": 1, "login": owner},
            }
        )

    async def list_branches(self, token: str, owner: str, repo: str) -> list:
        from app.infrastructure.github.models import GHBranch

        return [GHBranch.model_validate({"name": "main"})]

    async def create_branch(self, token: str, owner: str, repo: str, *, name: str, from_sha: str):
        return None

    async def list_commits(self, token: str, owner: str, repo: str, *, sha: str | None = None):
        from app.infrastructure.github.models import GHCommit

        return [
            GHCommit.model_validate(
                {
                    "sha": "abc123",
                    "message": "commit",
                    "author": {"login": "dev", "name": "Dev", "email": "dev@e.com"},
                }
            )
        ]

    async def merge_branch(self, token: str, owner: str, repo: str, *, base: str, head: str):
        from app.infrastructure.github.models import GHCommit

        return GHCommit.model_validate(
            {
                "sha": "merged",
                "message": "merge",
                "author": {"login": "dev", "name": "Dev", "email": "dev@e.com"},
            }
        )

    async def list_pull_requests(self, token: str, owner: str, repo: str, *, state: str = "open"):
        from app.infrastructure.github.models import GHPullRequest

        return [
            GHPullRequest.model_validate(
                {"id": 1, "number": 1, "state": state, "title": "PR", "html_url": ""}
            )
        ]

    async def get_pull_request(self, token: str, owner: str, repo: str, number: int):
        from app.infrastructure.github.models import GHPullRequest

        return GHPullRequest.model_validate(
            {"id": 1, "number": number, "state": "open", "title": "PR", "html_url": ""}
        )

    async def create_pull_request(
        self, token: str, owner: str, repo: str, *, title, head, base, body=None
    ):
        from app.infrastructure.github.models import GHPullRequest

        return GHPullRequest.model_validate(
            {"id": 1, "number": 2, "state": "open", "title": title, "html_url": ""}
        )

    async def merge_pull_request(
        self, token: str, owner: str, repo: str, number: int, *, merge_method: str = "merge"
    ):
        from app.infrastructure.github.models import GHPullRequest

        return GHPullRequest.model_validate(
            {"id": 1, "number": number, "state": "merged", "title": "PR", "html_url": ""}
        )

    async def request_reviewers(self, token: str, owner: str, repo: str, number: int, *, reviewers):
        return None

    async def submit_review(self, token: str, owner: str, repo: str, number: int, *, body, event):
        return {"state": event, "body": body}

    async def list_issues(self, token: str, owner: str, repo: str, *, state: str = "open"):
        from app.infrastructure.github.models import GHIssue

        return [
            GHIssue.model_validate(
                {"id": 1, "number": 1, "state": state, "title": "Issue", "html_url": ""}
            )
        ]

    async def get_issue(self, token: str, owner: str, repo: str, number: int):
        from app.infrastructure.github.models import GHIssue

        return GHIssue.model_validate(
            {"id": 1, "number": number, "state": "open", "title": "Issue", "html_url": ""}
        )

    async def create_issue(self, token: str, owner: str, repo: str, *, title, body=None):
        from app.infrastructure.github.models import GHIssue

        return GHIssue.model_validate(
            {"id": 2, "number": 5, "state": "open", "title": title, "html_url": ""}
        )

    async def update_issue(self, token: str, owner: str, repo: str, number: int, **fields):
        from app.infrastructure.github.models import GHIssue

        return GHIssue.model_validate(
            {
                "id": 3,
                "number": number,
                "state": fields.get("state", "open"),
                "title": "Issue",
                "html_url": "",
            }
        )

    async def comment_on_issue(self, token: str, owner: str, repo: str, number: int, *, body):
        from app.infrastructure.github.models import GHComment

        return GHComment.model_validate({"id": 1, "body": body, "html_url": ""})

    async def list_releases(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHRelease

        return [GHRelease.model_validate({"id": 1, "tag_name": "v1"})]

    async def create_release(self, token: str, owner: str, repo: str, **payload):
        from app.infrastructure.github.models import GHRelease

        return GHRelease.model_validate({"id": 1, "tag_name": payload.get("tag_name", "v1")})

    async def list_labels(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHLabels

        return [GHLabels.model_validate({"id": 1, "name": "bug", "color": "d73a4a"})]

    async def create_label(
        self, token: str, owner: str, repo: str, *, name, color, description=None
    ):
        from app.infrastructure.github.models import GHLabels

        return GHLabels.model_validate({"id": 1, "name": name, "color": color})

    async def list_milestones(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHMilestone

        return [GHMilestone.model_validate({"id": 1, "number": 1, "title": "M1"})]

    async def create_milestone(self, token: str, owner: str, repo: str, *, title, due_on=None):
        from app.infrastructure.github.models import GHMilestone

        return GHMilestone.model_validate({"id": 1, "number": 1, "title": title})

    async def list_workflows(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHWorkflow

        return [
            GHWorkflow.model_validate({"id": 1, "name": "ci", "path": ".github/workflows/ci.yml"})
        ]

    async def dispatch_workflow(
        self, token: str, owner: str, repo: str, *, workflow_id, ref, inputs=None
    ):
        return None

    async def list_workflow_runs(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHWorkflowRun

        return [GHWorkflowRun.model_validate({"id": 1, "name": "run"})]

    async def list_teams(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHTeam

        return [GHTeam.model_validate({"id": 1, "slug": "core", "name": "Core"})]

    async def list_collaborators(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHUser

        return [GHUser.model_validate({"id": 1, "login": "dev"})]

    async def list_discussions(self, token: str, owner: str, repo: str):
        from app.infrastructure.github.models import GHDiscussion

        return [GHDiscussion.model_validate({"id": "disc_1", "number": 1, "title": "D"})]

    async def create_repository(self, token: str, **payload):
        from app.infrastructure.github.models import GHRepository

        return GHRepository.model_validate(
            {
                "id": 10,
                "full_name": f"dev/{payload.get('name', 'repo')}",
                "name": payload.get("name", "repo"),
                "html_url": "",
                "owner": {"id": 1, "login": "dev"},
            }
        )

    async def delete_repository(self, token: str, owner: str, repo: str):
        return None

    async def fork_repository(self, token: str, owner: str, repo: str, *, organization=None):
        from app.infrastructure.github.models import GHRepository

        return GHRepository.model_validate(
            {
                "id": 11,
                "full_name": f"dev/{repo}-fork",
                "name": f"{repo}-fork",
                "html_url": "",
                "owner": {"id": 1, "login": "dev"},
            }
        )

    async def aclose(self) -> None:
        return None


def _tok_id(token: str) -> int:
    return int(hash(token) % 100000)


@pytest.fixture
def settings() -> Settings:
    return _test_settings()


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def vault(settings: Settings):
    from app.core.security import configure_vault

    return configure_vault(settings)


@pytest.fixture
def fake_github(settings: Settings) -> FakeGitHubClient:
    return FakeGitHubClient(settings)


@pytest.fixture
def app(settings: Settings, fake_redis: FakeRedis, fake_github: FakeGitHubClient):
    from app.main import make_app

    app = make_app(settings)
    app.state.redis = fake_redis  # type: ignore[attr-defined]
    app.state.github = fake_github  # type: ignore[attr-defined]
    app.state.vault = None  # replaced below

    from app.core.security import TokenVault

    app.state.vault = TokenVault(settings.TOKEN_ENCRYPTION_KEY)  # type: ignore[attr-defined]

    async def _init():
        from app.infrastructure.db.session import Database

        db = Database(settings)
        await db.init_db()
        app.state.db = db  # type: ignore[attr-defined]

    import asyncio

    asyncio.run(_init())
    return app


@pytest.fixture
async def client(app):
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _mock_github_token_endpoint():
    """Mock the GitHub OAuth access-token exchange so tests never hit the network."""
    import respx

    with respx.mock:
        respx.post("https://github.com/login/oauth/access_token").mock(
            return_value=respx.MockResponse(
                200,
                json={
                    "access_token": "gho_test_access_token",
                    "token_type": "bearer",
                    "scope": "read:user user:email",
                },
            )
        )
        yield
