"""Unit tests: GitHub API client REST + GraphQL helpers, ETag caching, search."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
import respx

from app.core.config import Settings
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.github.exceptions import (
    GitHubAuthError,
    GitHubClientError,
    GitHubConflictError,
    GitHubNotFoundError,
    GitHubValidationError,
    normalize_github_error,
    to_domain_exception,
)


def _settings() -> Settings:
    return Settings(
        APP_ENV="testing",
        SECRET_KEY="k" * 32,
        TOKEN_ENCRYPTION_KEY="d" * 64,
        DATABASE_URL="sqlite+aiosqlite:///:memory:",
        REDIS_URL="redis://fake",
        GITHUB_CLIENT_ID="cid",
        GITHUB_CLIENT_SECRET="csec",
        GITHUB_REDIRECT_URI="http://testserver/api/v1/auth/oauth/github/callback",
        GITHUB_API_BASE_URL="https://api.github.com",
        GITHUB_WEB_BASE_URL="https://github.com",
        GH_RETRY_MAX_ATTEMPTS=3,
        GH_RETRY_BASE_BACKOFF=0.01,
        GH_MAX_RETRY_WAIT_SECONDS=0.02,
    )


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.client = self

    async def set_json(self, key: str, value, ttl: int | None = None) -> None:
        import json

        self.store[key] = json.dumps(value)

    async def get_json(self, key: str):
        import json

        raw = self.store.get(key)
        return json.loads(raw) if raw else None

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


def _repo_payload(name: str = "repo", owner: str = "a", rid: int = 1) -> dict:
    return {
        "id": rid,
        "full_name": f"{owner}/{name}",
        "name": name,
        "html_url": f"https://github.com/{owner}/{name}",
        "owner": {"id": 1, "login": owner},
        "default_branch": "main",
        "visibility": "private",
        "created_at": "2024-01-01T00:00:00Z",
    }


def _commit_payload(sha: str = "abc123") -> dict:
    return {
        "sha": sha,
        "commit": {"author": {"date": "2024-01-02T00:00:00Z"}, "message": "hi"},
    }


@pytest.mark.asyncio
async def test_get_user_typed(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user").mock(
        respx.MockResponse(200, json={"id": 7, "login": "octocat", "name": "The Octo"})
    )
    user = await client.get_user("tok")
    assert user.id == 7
    assert user.login == "octocat"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_user_emails_and_primary(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    emails = [
        {"email": "primary@example.com", "primary": True, "verified": True},
        {"email": "other@example.com", "primary": False, "verified": True},
    ]
    respx_mock.get("https://api.github.com/user/emails").mock(respx.MockResponse(200, json=emails))
    got = await client.get_user_emails("tok")
    assert len(got) == 2
    assert got[0].email == "primary@example.com"
    assert await client.get_primary_email("tok") == "primary@example.com"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_primary_email_fallback_and_none(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user/emails").mock(
        side_effect=[
            respx.MockResponse(
                200, json=[{"email": "p@e.com", "primary": True, "verified": False}]
            ),
            respx.MockResponse(200, json=[]),
        ]
    )
    assert await client.get_primary_email("tok") == "p@e.com"
    assert await client.get_primary_email("tok") is None
    await client.aclose()


@pytest.mark.asyncio
async def test_list_organizations(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user/orgs").mock(
        respx.MockResponse(200, json=[{"id": 1, "login": "org1"}])
    )
    orgs = await client.list_organizations("tok")
    assert orgs[0].login == "org1"
    await client.aclose()


@pytest.mark.asyncio
async def test_list_repositories_filters(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user/repos").mock(
        respx.MockResponse(200, json=[_repo_payload()])
    )
    repos = await client.list_repositories("tok", visibility="public", affiliation="owner")
    assert repos[0].name == "repo"
    assert respx_mock.calls[0].request.url.params["visibility"] == "public"
    await client.aclose()


@pytest.mark.asyncio
async def test_list_repositories_page_totals(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user/repos").mock(
        respx.MockResponse(
            200,
            json=[_repo_payload("r1", rid=1), _repo_payload("r2", rid=2)],
            headers={
                "Link": (
                    '<https://api.github.com/user/repos?page=2>; rel="next", '
                    '<https://api.github.com/user/repos?page=3>; rel="last"'
                )
            },
        )
    )
    page = await client.list_repositories_page("tok", page=1, per_page=2)
    assert len(page.items) == 2
    assert page.total_count == 3 * 2
    assert "page=2" in (page.next_page or "")

    # Last page: exact total derived from partial page.
    respx_mock.reset()
    respx_mock.get("https://api.github.com/user/repos").mock(
        respx.MockResponse(
            200,
            json=[_repo_payload("r9", rid=9)],
            headers={"Link": '<https://api.github.com/user/repos?page=5>; rel="last"'},
        )
    )
    last = await client.list_repositories_page("tok", page=5, per_page=2)
    assert last.total_count == 4 * 2 + 1
    await client.aclose()


@pytest.mark.asyncio
async def test_list_repositories_page_no_last(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/user/repos").mock(
        respx.MockResponse(200, json=[_repo_payload()])
    )
    page = await client.list_repositories_page("tok", page=1, per_page=30)
    assert page.total_count is None
    assert page.next_page is None
    await client.aclose()


@pytest.mark.asyncio
async def test_search_repositories_page(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/search/repositories").mock(
        respx.MockResponse(
            200,
            json={
                "total_count": 1,
                "items": [_repo_payload("found", rid=42)],
            },
        )
    )
    page = await client.list_repositories_page("tok", page=1, per_page=12, q="found user:octo")
    assert len(page.items) == 1
    assert page.items[0].name == "found"
    assert page.total_count == 1
    assert page.next_page is None
    await client.aclose()


@pytest.mark.asyncio
async def test_list_assigned_issues(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/issues").mock(
        respx.MockResponse(
            200,
            json=[
                {
                    "id": 5,
                    "number": 12,
                    "state": "open",
                    "title": "Assigned",
                    "html_url": "https://github.com/a/repo/issues/12",
                    "repository": {"full_name": "a/repo"},
                }
            ],
        )
    )
    issues = await client.list_assigned_issues("tok", state="open")
    assert len(issues) == 1
    assert issues[0].number == 12
    assert issues[0].repository["full_name"] == "a/repo"
    await client.aclose()


@pytest.mark.asyncio
async def test_get_commit_count_for_user_cache_hit_and_miss(respx_mock):
    redis = _FakeRedis()
    client = GitHubAPIClient(_settings(), redis)
    # Cache hit first.
    redis.store["gh:commitcount:o/r:alice"] = "42"
    assert await client.get_commit_count_for_user("tok", "o", "r", "alice") == 42
    # Miss → REST fallback.
    respx_mock.get("https://api.github.com/repos/o/r/commits").mock(
        respx.MockResponse(
            200,
            json=[_commit_payload()],
            headers={"Link": '<https://api.github.com/repos/o/r/commits?page=9>; rel="last"'},
        )
    )
    assert await client.get_commit_count_for_user("tok", "o", "r", "bob") == 9
    assert redis.store["gh:commitcount:o/r:bob"] == "9"
    # No last link → count from body.
    respx_mock.reset()
    respx_mock.get("https://api.github.com/repos/o/r/commits").mock(
        respx.MockResponse(200, json=[_commit_payload(), _commit_payload("def")])
    )
    assert await client.get_commit_count_for_user("tok", "o", "r", "carol") == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_get_contributions_summary_cached_and_fetched(respx_mock):
    redis = _FakeRedis()
    client = GitHubAPIClient(_settings(), redis)
    key = f"gh:contrib:alice:{datetime.now(UTC).strftime('%Y')}"
    redis.store[key] = '{"commits": 5, "pull_requests": 1, "issues": 2, "reviews": 0, "total": 8}'
    summary = await client.get_contributions_summary("tok", "alice")
    assert summary["commits"] == 5
    # Live fetch.
    respx_mock.post("https://api.github.com/graphql").mock(
        respx.MockResponse(
            200,
            json={
                "data": {
                    "user": {
                        "contributionsCollection": {
                            "totalCommitContributions": 10,
                            "totalPullRequestContributions": 2,
                            "totalIssueContributions": 3,
                            "totalPullRequestReviewContributions": 4,
                            "contributionCalendar": {"totalContributions": 19},
                        }
                    }
                }
            },
        )
    )
    fresh = await client.get_contributions_summary("tok", "bob")
    assert fresh == {"commits": 10, "pull_requests": 2, "issues": 3, "reviews": 4, "total": 19}
    await client.aclose()


@pytest.mark.asyncio
async def test_get_contribution_calendar(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.post("https://api.github.com/graphql").mock(
        respx.MockResponse(
            200,
            json={
                "data": {
                    "user": {
                        "contributionsCollection": {
                            "totalCommitContributions": 3,
                            "totalPullRequestContributions": 0,
                            "totalIssueContributions": 0,
                            "totalPullRequestReviewContributions": 0,
                            "totalRepositoryContributions": 1,
                            "contributionCalendar": {
                                "totalContributions": 4,
                                "weeks": [
                                    {
                                        "contributionDays": [
                                            {"date": "2024-01-01", "contributionCount": 2},
                                            {"date": "2024-01-02", "contributionCount": 1},
                                        ]
                                    }
                                ],
                            },
                        }
                    }
                }
            },
        )
    )
    cal = await client.get_contribution_calendar(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert cal["total"] == 4
    assert cal["days"] == [
        {"date": "2024-01-01", "count": 2},
        {"date": "2024-01-02", "count": 1},
    ]
    assert cal["breakdown"]["commits"] == 3
    # Future end date clamped to today (same mock response is served).
    future = await client.get_contribution_calendar(
        "tok", "alice", date(2030, 1, 1), date(2031, 1, 1)
    )
    assert future["days"] == cal["days"]
    await client.aclose()


@pytest.mark.asyncio
async def test_get_commit_contribution_days(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/search/commits").mock(
        respx.MockResponse(
            200,
            json={
                "total_count": 1,
                "items": [
                    {
                        "commit": {"author": {"date": "2024-01-05T10:00:00Z"}},
                        "repository": {"full_name": "a/r"},
                    }
                ],
            },
        )
    )
    days, repos = await client.get_commit_contribution_days(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert days == {"2024-01-05": 1}
    assert repos == {"a/r": 1}
    await client.aclose()


@pytest.mark.asyncio
async def test_get_issue_contribution_days_modes(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/search/issues").mock(
        respx.MockResponse(
            200,
            json={
                "total_count": 1,
                "items": [
                    {"created_at": "2024-01-06T00:00:00Z", "updated_at": "2024-01-07T00:00:00Z"}
                ],
            },
        )
    )
    opened = await client.get_issue_contribution_days(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert opened == {"2024-01-06": 1}
    prs = await client.get_issue_contribution_days(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31), pr_only=True
    )
    assert prs == {"2024-01-06": 1}
    reviewed = await client.get_issue_contribution_days(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31), reviewed=True
    )
    assert reviewed == {"2024-01-07": 1}
    await client.aclose()


@pytest.mark.asyncio
async def test_get_repository_creation_days(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    from app.infrastructure.github.models import GHRepository

    repos = [
        GHRepository.model_validate({**_repo_payload("a"), "created_at": "2024-01-10T00:00:00Z"}),
        GHRepository.model_validate({**_repo_payload("b"), "created_at": "2023-05-01T00:00:00Z"}),
    ]
    days = await client.get_repository_creation_days(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31), repos=repos
    )
    assert days == {"2024-01-10": 1}
    # repos=None → falls back to list_repositories.
    respx_mock.get("https://api.github.com/user/repos").mock(
        respx.MockResponse(200, json=[{**_repo_payload("c"), "created_at": "2024-01-20T00:00:00Z"}])
    )
    via_fetch = await client.get_repository_creation_days(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31)
    )
    assert via_fetch == {"2024-01-20": 1}
    await client.aclose()


@pytest.mark.asyncio
async def test_get_action_days(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/repos/a/repo/actions/runs").mock(
        respx.MockResponse(
            200,
            json={
                "workflow_runs": [
                    {"created_at": "2024-01-03T00:00:00Z"},
                    {"created_at": "2024-01-03T01:00:00Z"},
                ]
            },
        )
    )
    from app.infrastructure.github.models import GHRepository

    repos = [GHRepository.model_validate(_repo_payload())]
    days = await client.get_action_days(
        "tok", "alice", date(2024, 1, 1), date(2024, 1, 31), repos=repos
    )
    assert days == {"2024-01-03": 2}
    await client.aclose()


@pytest.mark.asyncio
async def test_repository_crud(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/repos/a/repo").mock(
        respx.MockResponse(200, json=_repo_payload())
    )
    repo = await client.get_repository("tok", "a", "repo")
    assert repo.name == "repo"

    respx_mock.post("https://api.github.com/user/repos").mock(
        respx.MockResponse(201, json=_repo_payload("new"))
    )
    created = await client.create_repository("tok", name="new", private=True)
    assert created.name == "new"

    respx_mock.delete("https://api.github.com/repos/a/repo").mock(respx.MockResponse(204))
    await client.delete_repository("tok", "a", "repo")

    respx_mock.post("https://api.github.com/repos/a/repo/forks").mock(
        respx.MockResponse(202, json=_repo_payload("fork"))
    )
    forked = await client.fork_repository("tok", "a", "repo", organization="ghorg")
    assert forked.name == "fork"
    # fork without org → json_body None.
    respx_mock.reset()
    respx_mock.post("https://api.github.com/repos/a/repo/forks").mock(
        respx.MockResponse(202, json=_repo_payload("fork2"))
    )
    await client.fork_repository("tok", "a", "repo")
    await client.aclose()


@pytest.mark.asyncio
async def test_branches_and_commits(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/repos/a/repo/branches").mock(
        respx.MockResponse(200, json=[{"name": "main", "commit": {"sha": "s"}}])
    )
    branches = await client.list_branches("tok", "a", "repo")
    assert branches[0].name == "main"

    respx_mock.get("https://api.github.com/repos/a/repo/branches/main").mock(
        respx.MockResponse(200, json={"name": "main", "commit": {"sha": "s"}, "protected": True})
    )
    branch = await client.get_branch("tok", "a", "repo", "main")
    assert branch.protected is True

    respx_mock.post("https://api.github.com/repos/a/repo/git/refs").mock(
        respx.MockResponse(201, json={"ref": "refs/heads/feat"})
    )
    await client.create_branch("tok", "a", "repo", name="feat", from_sha="s")

    respx_mock.get("https://api.github.com/repos/a/repo/commits").mock(
        respx.MockResponse(200, json=[_commit_payload()])
    )
    commits = await client.list_commits("tok", "a", "repo", sha="main")
    assert commits[0].sha == "abc123"

    respx_mock.get("https://api.github.com/repos/a/repo/commits/main").mock(
        respx.MockResponse(200, json=_commit_payload())
    )
    commit = await client.get_commit("tok", "a", "repo", "main")
    assert commit.sha == "abc123"

    respx_mock.post("https://api.github.com/repos/a/repo/git/commits").mock(
        respx.MockResponse(201, json=_commit_payload("def"))
    )
    created = await client.create_commit("tok", "a", "repo", message="m", tree="t", parents=["p"])
    assert created.sha == "def"

    respx_mock.post("https://api.github.com/repos/a/repo/merges").mock(
        respx.MockResponse(201, json=_commit_payload("ghi"))
    )
    merged = await client.merge_branch(
        "tok", "a", "repo", base="main", head="feat", commit_message="merge"
    )
    assert merged.sha == "ghi"
    await client.aclose()


@pytest.mark.asyncio
async def test_pull_requests(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    pr = {
        "id": 1,
        "number": 3,
        "state": "open",
        "title": "PR",
        "html_url": "https://github.com/a/repo/pull/3",
    }
    respx_mock.get("https://api.github.com/repos/a/repo/pulls").mock(
        respx.MockResponse(200, json=[pr])
    )
    prs = await client.list_pull_requests("tok", "a", "repo", state="open")
    assert prs[0].number == 3

    respx_mock.get("https://api.github.com/repos/a/repo/pulls/3").mock(
        respx.MockResponse(200, json=pr)
    )
    got = await client.get_pull_request("tok", "a", "repo", 3)
    assert got.title == "PR"

    respx_mock.post("https://api.github.com/repos/a/repo/pulls").mock(
        respx.MockResponse(201, json={**pr, "number": 4})
    )
    created = await client.create_pull_request(
        "tok", "a", "repo", title="PR", head="f", base="m", body="b"
    )
    assert created.number == 4

    respx_mock.put("https://api.github.com/repos/a/repo/pulls/4/merge").mock(
        respx.MockResponse(200, json={**pr, "number": 4, "merged": True})
    )
    merged = await client.merge_pull_request("tok", "a", "repo", 4, merge_method="squash")
    assert merged.merged is True

    respx_mock.post("https://api.github.com/repos/a/repo/pulls/4/requested_reviewers").mock(
        respx.MockResponse(201, json={})
    )
    await client.request_reviewers("tok", "a", "repo", 4, reviewers=["alice"])

    respx_mock.post("https://api.github.com/repos/a/repo/pulls/4/reviews").mock(
        respx.MockResponse(200, json={"id": 99, "state": "APPROVED"})
    )
    review = await client.submit_review("tok", "a", "repo", 4, body="LGTM", event="APPROVE")
    assert review["state"] == "APPROVED"
    await client.aclose()


@pytest.mark.asyncio
async def test_issues(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    issue = {"id": 1, "number": 5, "state": "open", "title": "Bug", "html_url": ""}
    respx_mock.get("https://api.github.com/repos/a/repo/issues").mock(
        respx.MockResponse(200, json=[issue])
    )
    issues = await client.list_issues("tok", "a", "repo", state="all")
    assert issues[0].title == "Bug"

    respx_mock.get("https://api.github.com/repos/a/repo/issues/5").mock(
        respx.MockResponse(200, json=issue)
    )
    got = await client.get_issue("tok", "a", "repo", 5)
    assert got.number == 5

    respx_mock.post("https://api.github.com/repos/a/repo/issues").mock(
        respx.MockResponse(201, json={**issue, "number": 6})
    )
    created = await client.create_issue("tok", "a", "repo", title="New", body="details")
    assert created.number == 6

    respx_mock.patch("https://api.github.com/repos/a/repo/issues/6").mock(
        respx.MockResponse(200, json={**issue, "number": 6, "state": "closed"})
    )
    updated = await client.update_issue("tok", "a", "repo", 6, state="closed")
    assert updated.state == "closed"
    closed = await client.close_issue("tok", "a", "repo", 6)
    assert closed.state == "closed"

    respx_mock.post("https://api.github.com/repos/a/repo/issues/6/comments").mock(
        respx.MockResponse(201, json={"id": 1, "body": "comment", "html_url": ""})
    )
    comment = await client.comment_on_issue("tok", "a", "repo", 6, body="comment")
    assert comment.body == "comment"
    await client.aclose()


@pytest.mark.asyncio
async def test_releases_labels_milestones(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/repos/a/repo/releases").mock(
        respx.MockResponse(200, json=[{"id": 1, "tag_name": "v1", "html_url": ""}])
    )
    releases = await client.list_releases("tok", "a", "repo")
    assert releases[0].tag_name == "v1"

    respx_mock.post("https://api.github.com/repos/a/repo/releases").mock(
        respx.MockResponse(201, json={"id": 2, "tag_name": "v2"})
    )
    rel = await client.create_release("tok", "a", "repo", tag_name="v2", name="Two")
    assert rel.tag_name == "v2"

    respx_mock.get("https://api.github.com/repos/a/repo/labels").mock(
        respx.MockResponse(200, json=[{"id": 1, "name": "bug", "color": "d73a4a"}])
    )
    labels = await client.list_labels("tok", "a", "repo")
    assert labels[0].name == "bug"

    respx_mock.post("https://api.github.com/repos/a/repo/labels").mock(
        respx.MockResponse(201, json={"id": 2, "name": "feat", "color": "00ff00"})
    )
    label = await client.create_label(
        "tok", "a", "repo", name="feat", color="00ff00", description="d"
    )
    assert label.name == "feat"

    respx_mock.get("https://api.github.com/repos/a/repo/milestones").mock(
        respx.MockResponse(200, json=[{"id": 1, "number": 1, "title": "M1"}])
    )
    milestones = await client.list_milestones("tok", "a", "repo")
    assert milestones[0].title == "M1"

    respx_mock.post("https://api.github.com/repos/a/repo/milestones").mock(
        respx.MockResponse(201, json={"id": 2, "number": 2, "title": "M2"})
    )
    ms = await client.create_milestone(
        "tok", "a", "repo", title="M2", due_on="2024-12-01T00:00:00Z"
    )
    assert ms.number == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_workflows_and_teams(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/repos/a/repo/actions/workflows").mock(
        respx.MockResponse(
            200, json={"workflows": [{"id": 1, "name": "ci", "path": ".github/workflows/ci.yml"}]}
        )
    )
    workflows = await client.list_workflows("tok", "a", "repo")
    assert workflows[0].name == "ci"

    respx_mock.post("https://api.github.com/repos/a/repo/actions/workflows/1/dispatches").mock(
        respx.MockResponse(204)
    )
    await client.dispatch_workflow(
        "tok", "a", "repo", workflow_id="1", ref="main", inputs={"x": "y"}
    )

    respx_mock.post("https://api.github.com/repos/a/repo/actions/workflows/2/dispatches").mock(
        respx.MockResponse(204)
    )
    await client.dispatch_workflow("tok", "a", "repo", workflow_id="2", ref="main")

    respx_mock.get("https://api.github.com/repos/a/repo/actions/runs").mock(
        respx.MockResponse(200, json={"workflow_runs": [{"id": 1, "name": "run1"}]})
    )
    runs = await client.list_workflow_runs("tok", "a", "repo")
    assert runs[0].name == "run1"

    respx_mock.get("https://api.github.com/repos/a/repo/teams").mock(
        respx.MockResponse(200, json=[{"id": 1, "name": "t", "slug": "t"}])
    )
    teams = await client.list_teams("tok", "a", "repo")
    assert teams[0].slug == "t"

    respx_mock.get("https://api.github.com/repos/a/repo/collaborators").mock(
        respx.MockResponse(200, json=[{"id": 1, "login": "collab"}])
    )
    collabs = await client.list_collaborators("tok", "a", "repo")
    assert collabs[0].login == "collab"

    respx_mock.get("https://api.github.com/orgs/a/packages").mock(
        respx.MockResponse(200, json=[{"id": 1, "name": "pkg", "package_type": "container"}])
    )
    packages = await client.list_packages("tok", "a", "repo")
    assert packages[0].name == "pkg"
    await client.aclose()


@pytest.mark.asyncio
async def test_list_discussions_paginated(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    node = {"id": "D1", "number": 1, "title": "Hi", "author": {"login": "a"}}
    respx_mock.post("https://api.github.com/graphql").mock(
        side_effect=[
            respx.MockResponse(
                200,
                json={
                    "data": {
                        "repository": {
                            "discussions": {
                                "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
                                "nodes": [node],
                            }
                        }
                    }
                },
            ),
            respx.MockResponse(
                200,
                json={
                    "data": {
                        "repository": {
                            "discussions": {
                                "pageInfo": {"hasNextPage": False, "endCursor": None},
                                "nodes": [node],
                            }
                        }
                    }
                },
            ),
        ]
    )
    discussions = await client.list_discussions("tok", "a", "repo")
    assert len(discussions) == 2
    # Empty repository data breaks out of loop.
    respx_mock.reset()
    respx_mock.post("https://api.github.com/graphql").mock(
        respx.MockResponse(200, json={"data": {}})
    )
    assert await client.list_discussions("tok", "a", "repo") == []
    await client.aclose()


@pytest.mark.asyncio
async def test_get_rate_limit(respx_mock):
    client = GitHubAPIClient(_settings(), _FakeRedis())
    respx_mock.get("https://api.github.com/rate_limit").mock(
        respx.MockResponse(200, json={"resources": {"core": {"limit": 5000}}})
    )
    rl = await client.get_rate_limit("tok")
    assert rl.resources["core"]["limit"] == 5000
    await client.aclose()


@pytest.mark.asyncio
async def test_etag_header_key_and_safe_json():
    client = GitHubAPIClient(_settings(), _FakeRedis())
    key = client._etag_key("/user", "tok", {"a": 1})
    assert client._etag_header_key("/user", "tok", {"a": 1}) == f"{key}:hdr"
    assert key.startswith("gh:cache:")
    await client.aclose()


def test_normalize_github_error_mapping():
    auth = normalize_github_error(401, {"message": "bad creds"})
    assert isinstance(auth, GitHubAuthError)
    nf = normalize_github_error(404, {"message": "nope"})
    assert isinstance(nf, GitHubNotFoundError)
    conflict = normalize_github_error(409, {})
    assert isinstance(conflict, GitHubConflictError)
    valid = normalize_github_error(422, {"message": "invalid"})
    assert isinstance(valid, GitHubValidationError)
    server = normalize_github_error(503, {})
    assert isinstance(server, GitHubClientError)
    assert server.status_code == 503
    other = normalize_github_error(418, {})
    assert isinstance(other, GitHubClientError)
    assert other.body == {}


def test_to_domain_exception_mapping():
    from app.core.exceptions import (
        AuthorizationError,
        ConflictError,
        GitHubProviderError,
        NotFoundError,
        ValidationFailure,
    )
    from app.infrastructure.github.exceptions import (
        GitHubAuthError,
        GitHubConflictError,
        GitHubForbiddenError,
        GitHubRateLimitError,
        GitHubValidationError,
    )

    rl = to_domain_exception(GitHubRateLimitError("rl", reset_at=123))
    assert rl.details.get("reset_at") == 123
    assert isinstance(to_domain_exception(GitHubAuthError("a")), AuthorizationError)
    assert isinstance(to_domain_exception(GitHubForbiddenError("f")), AuthorizationError)
    assert isinstance(to_domain_exception(GitHubNotFoundError("n")), NotFoundError)
    assert isinstance(to_domain_exception(GitHubValidationError("v")), ValidationFailure)
    assert isinstance(to_domain_exception(GitHubConflictError("c")), ConflictError)
    assert isinstance(to_domain_exception(GitHubClientError("x")), GitHubProviderError)
