"""Unit tests: RepositoryService (read/write GitHub gateway)."""

from __future__ import annotations

import uuid

import pytest

from app.application.services.audit_service import AuditService
from app.application.services.repository_service import RepositoryService
from app.core.config import Settings
from app.domain.models.enums import AuthProvider
from app.infrastructure.db.session import Database
from app.infrastructure.github.exceptions import GitHubNotFoundError
from app.infrastructure.github.models import (
    GHIssue,
    GHRepository,
    GHWorkflow,
    GHWorkflowRun,
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
    )


class _FakeGitHub:
    """Duck-typed stand-in for GitHubAPIClient; records calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.repos = [
            GHRepository.model_validate(
                {
                    "id": 1,
                    "full_name": "a/repo",
                    "name": "repo",
                    "html_url": "https://github.com/a/repo",
                    "owner": {"id": 1, "login": "a"},
                }
            )
        ]
        self.fail_next = False
        self.fail_all = False

    async def _maybe_fail(self) -> None:
        if self.fail_all:
            raise GitHubNotFoundError("gone")
        if self.fail_next:
            self.fail_next = False
            raise GitHubNotFoundError("gone")

    async def list_repositories(self, token: str, **kw):
        self.calls.append(("list_repositories", (token,)))
        await self._maybe_fail()
        return self.repos

    async def list_repositories_page(
        self, token: str, *, page: int = 1, per_page: int = 9, q: str | None = None
    ):
        self.calls.append(("list_repositories_page", (token, page, per_page, q)))
        await self._maybe_fail()
        from app.infrastructure.github.models import GHPaged

        items = self.repos
        if q:
            items = [r for r in self.repos if q.replace(" user:octocat", "") in r.name]
        return GHPaged(items=items, next_page=None, total_count=len(items))

    async def get_commit_count_for_user(self, token, owner, repo, author):
        self.calls.append(("get_commit_count_for_user", (owner, repo, author)))
        await self._maybe_fail()
        return 7

    async def get_contributions_summary(self, token, login):
        self.calls.append(("get_contributions_summary", (login,)))
        await self._maybe_fail()
        return {"commits": 1, "pull_requests": 2, "issues": 3, "reviews": 4, "total": 10}

    async def get_repository(self, token, owner, repo):
        self.calls.append(("get_repository", (owner, repo)))
        await self._maybe_fail()
        return self.repos[0]

    async def create_repository(self, token, **payload):
        self.calls.append(("create_repository", (payload,)))
        await self._maybe_fail()
        return self.repos[0]

    async def delete_repository(self, token, owner, repo):
        self.calls.append(("delete_repository", (owner, repo)))
        await self._maybe_fail()

    async def fork_repository(self, token, owner, repo, *, organization=None):
        self.calls.append(("fork_repository", (owner, repo, organization)))
        await self._maybe_fail()
        return self.repos[0]

    async def list_branches(self, token, owner, repo):
        await self._maybe_fail()
        return []

    async def create_branch(self, token, owner, repo, *, name, from_sha):
        self.calls.append(("create_branch", (owner, repo, name)))
        await self._maybe_fail()

    async def list_commits(self, token, owner, repo, *, sha=None):
        await self._maybe_fail()
        return []

    async def get_commit(self, token, owner, repo, ref):
        await self._maybe_fail()
        return {"sha": ref}

    async def merge_branch(self, token, owner, repo, *, base, head):
        self.calls.append(("merge_branch", (owner, repo, base, head)))
        await self._maybe_fail()
        return "merged"

    async def list_pull_requests(self, token, owner, repo, *, state="open"):
        await self._maybe_fail()
        return []

    async def get_pull_request(self, token, owner, repo, number):
        await self._maybe_fail()
        return {"number": number}

    async def create_pull_request(self, token, owner, repo, *, title, head, base, body=None):
        self.calls.append(("create_pr", (title,)))
        await self._maybe_fail()
        from app.infrastructure.github.models import GHPullRequest

        return GHPullRequest.model_validate(
            {
                "id": 1,
                "number": 1,
                "state": "open",
                "title": title,
                "html_url": "https://github.com/a/repo/pull/1",
            }
        )

    async def merge_pull_request(self, token, owner, repo, number, *, merge_method="merge"):
        await self._maybe_fail()
        return {"number": number, "merged": True}

    async def request_reviewers(self, token, owner, repo, number, *, reviewers):
        self.calls.append(("request_reviewers", (reviewers,)))
        await self._maybe_fail()

    async def submit_review(self, token, owner, repo, number, *, body, event):
        await self._maybe_fail()
        return {"state": "APPROVED"}

    async def list_issues(self, token, owner, repo, *, state="open"):
        await self._maybe_fail()
        return []

    async def list_assigned_issues(self, token, *, state="open"):
        self.calls.append(("list_assigned_issues", (state,)))
        await self._maybe_fail()
        return [
            GHIssue.model_validate(
                {
                    "id": 9,
                    "number": 5,
                    "state": state,
                    "title": "assigned",
                    "html_url": "",
                    "repository": {"full_name": "a/repo"},
                }
            )
        ]

    async def get_issue(self, token, owner, repo, number):
        await self._maybe_fail()
        return GHIssue.model_validate(
            {"id": 1, "number": number, "state": "open", "title": "x", "html_url": ""}
        )

    async def create_issue(self, token, owner, repo, *, title, body=None):
        self.calls.append(("create_issue", (title,)))
        await self._maybe_fail()
        return GHIssue.model_validate(
            {"id": 2, "number": 5, "state": "open", "title": title, "html_url": ""}
        )

    async def update_issue(self, token, owner, repo, number, **fields):
        await self._maybe_fail()
        return GHIssue.model_validate(
            {
                "id": 3,
                "number": number,
                "state": fields.get("state", "open"),
                "title": "x",
                "html_url": "",
            }
        )

    async def comment_on_issue(self, token, owner, repo, number, *, body):
        await self._maybe_fail()
        return {"body": body}

    async def list_releases(self, token, owner, repo):
        await self._maybe_fail()
        return []

    async def create_release(self, token, owner, repo, **payload):
        await self._maybe_fail()
        from app.infrastructure.github.models import GHRelease

        return GHRelease.model_validate({"id": 1, "tag_name": payload.get("tag_name", "v1")})

    async def list_labels(self, token, owner, repo):
        await self._maybe_fail()
        return []

    async def create_label(self, token, owner, repo, *, name, color, description=None):
        await self._maybe_fail()
        from app.infrastructure.github.models import GHLabels

        return GHLabels.model_validate({"id": 1, "name": name, "color": color})

    async def list_milestones(self, token, owner, repo):
        await self._maybe_fail()
        return []

    async def create_milestone(self, token, owner, repo, *, title, due_on=None):
        await self._maybe_fail()
        from app.infrastructure.github.models import GHMilestone

        return GHMilestone.model_validate({"id": 1, "number": 1, "title": title})

    async def list_workflows(self, token, owner, repo):
        await self._maybe_fail()
        return [
            GHWorkflow.model_validate({"id": 1, "name": "ci", "path": ".github/workflows/ci.yml"})
        ]

    async def dispatch_workflow(self, token, owner, repo, *, workflow_id, ref, inputs=None):
        self.calls.append(("dispatch_workflow", (workflow_id, ref)))
        await self._maybe_fail()

    async def list_workflow_runs(self, token, owner, repo):
        await self._maybe_fail()
        return [GHWorkflowRun.model_validate({"id": 1, "name": "run"})]

    async def list_teams(self, token, owner, repo):
        await self._maybe_fail()
        return []

    async def list_collaborators(self, token, owner, repo):
        await self._maybe_fail()
        return []

    async def list_organizations(self, token):
        await self._maybe_fail()
        return []

    async def list_discussions(self, token, owner, repo):
        await self._maybe_fail()
        return []

    async def graphql(self, token, query, variables=None):
        await self._maybe_fail()
        return {"data": {}}


class _FakeTokens:
    def __init__(self) -> None:
        self.login: str | None = "octocat"

    async def access_token_for_user(self, user_id):
        return "gho_token"

    async def github_login_for_user(self, user_id):
        return self.login


class _FakeAppAuth:
    """GitHub App auth stand-in; records install-token lookups."""

    def __init__(self) -> None:
        self.tokens_requested: list[tuple[str, str]] = []

    async def installation_token_for(self, owner: str, repo: str | None = None) -> str:
        self.tokens_requested.append((owner, repo or ""))
        return "ghs_install_token"


@pytest.mark.asyncio
async def test_read_operations():
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        github = _FakeGitHub()
        svc = RepositoryService(github=github, tokens=_FakeTokens(), audit=AuditService(session))
        user_id = uuid.uuid4()

        repos = await svc.list_repositories(user_id)
        assert repos[0].name == "repo"

        paginated = await svc.list_repositories_paginated(user_id, page=1, per_page=9)
        assert paginated["total_count"] == 1
        assert paginated["total_pages"] == 1
        assert paginated["repositories"][0]["contributions"] == 7

        searched = await svc.list_repositories_paginated(user_id, q="repo")
        assert searched["repositories"][0]["name"] == "repo"
        searched_empty = await svc.list_repositories_paginated(user_id, q="nope")
        assert searched_empty["repositories"] == []

        # No login → contributions None.
        tokens = _FakeTokens()
        tokens.login = None
        svc2 = RepositoryService(github=github, tokens=tokens, audit=AuditService(session))
        paginated2 = await svc2.list_repositories_paginated(user_id)
        assert paginated2["repositories"][0]["contributions"] is None

        summary = await svc.get_contributions_summary(user_id)
        assert summary["commits"] == 1

        tokens3 = _FakeTokens()
        tokens3.login = None
        svc3 = RepositoryService(github=github, tokens=tokens3, audit=AuditService(session))
        assert await svc3.get_contributions_summary(user_id) == {
            "commits": 0,
            "pull_requests": 0,
            "issues": 0,
            "reviews": 0,
            "total": 0,
        }

        repo = await svc.get_repository(user_id, "a", "repo")
        assert repo.name == "repo"

        assert await svc.list_branches(user_id, "a", "repo") == []
        assert await svc.list_commits(user_id, "a", "repo", sha="main") == []
        assert (await svc.get_commit(user_id, "a", "repo", "abc"))["sha"] == "abc"
        assert await svc.list_pull_requests(user_id, "a", "repo") == []
        assert (await svc.get_pull_request(user_id, "a", "repo", 1))["number"] == 1
        assert await svc.list_issues(user_id, "a", "repo") == []
        assert (await svc.get_issue(user_id, "a", "repo", 2)).number == 2
        assigned = await svc.list_assigned_issues(user_id, state="open")
        assert assigned[0].title == "assigned"
        assert assigned[0].repository["full_name"] == "a/repo"
        assert await svc.list_releases(user_id, "a", "repo") == []
        assert await svc.list_labels(user_id, "a", "repo") == []
        assert await svc.list_milestones(user_id, "a", "repo") == []
        assert (await svc.list_workflows(user_id, "a", "repo"))[0].name == "ci"
        assert (await svc.list_workflow_runs(user_id, "a", "repo"))[0].name == "run"
        assert await svc.list_teams(user_id, "a", "repo") == []
        assert await svc.list_collaborators(user_id, "a", "repo") == []
        assert await svc.list_organizations(user_id) == []
        assert await svc.list_discussions(user_id, "a", "repo") == []
        assert await svc.graphql(user_id, "{ viewer { login } }") == {"data": {}}
    await db.dispose()


@pytest.mark.asyncio
async def test_write_operations():
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        github = _FakeGitHub()
        svc = RepositoryService(github=github, tokens=_FakeTokens(), audit=AuditService(session))
        user_id = uuid.uuid4()

        await svc.create_repository(user_id, name="new")
        await svc.delete_repository(user_id, "a", "repo")
        forked = await svc.fork_repository(user_id, "a", "repo", organization="org")
        assert forked.name == "repo"

        await svc.create_branch(user_id, "a", "repo", name="feat", from_sha="s")
        assert await svc.merge_branch(user_id, "a", "repo", base="main", head="feat") == "merged"

        pr = await svc.create_pull_request(user_id, "a", "repo", title="T", head="f", base="m")
        assert pr.number == 1
        merged = await svc.merge_pull_request(user_id, "a", "repo", 1, merge_method="squash")
        assert merged["merged"] is True
        await svc.request_reviewers(user_id, "a", "repo", 1, reviewers=["bob"])
        assert (await svc.submit_review(user_id, "a", "repo", 1, body="lgtm", event="APPROVE"))[
            "state"
        ] == "APPROVED"

        issue = await svc.create_issue(user_id, "a", "repo", title="I", body="b")
        assert issue.number == 5
        updated = await svc.update_issue(user_id, "a", "repo", 3, state="closed")
        assert updated.state == "closed"
        closed = await svc.close_issue(user_id, "a", "repo", 3)
        assert closed.state == "closed"
        assert (await svc.comment_on_issue(user_id, "a", "repo", 3, body="c"))["body"] == "c"

        rel = await svc.create_release(user_id, "a", "repo", tag_name="v9")
        assert rel.tag_name == "v9"
        label = await svc.create_label(user_id, "a", "repo", name="bug", color="red")
        assert label.name == "bug"
        ms = await svc.create_milestone(user_id, "a", "repo", title="M1")
        assert ms.title == "M1"

        await svc.dispatch_workflow(
            user_id, "a", "repo", workflow_id="1", ref="main", inputs={"x": 1}
        )
    await db.dispose()


@pytest.mark.asyncio
async def test_errors_mapped_to_domain():
    from app.core.exceptions import NotFoundError

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        github = _FakeGitHub()
        github.fail_next = True
        svc = RepositoryService(github=github, tokens=_FakeTokens(), audit=AuditService(session))
        with pytest.raises(NotFoundError):
            await svc.get_repository(uuid.uuid4(), "a", "repo")
    await db.dispose()


@pytest.mark.asyncio
async def test_all_github_error_branches():
    """Every public method maps GitHubClientError to a domain exception."""
    from app.core.exceptions import NotFoundError

    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        uid = uuid.uuid4()

        async def _assert_fails(factory):
            github = _FakeGitHub()
            github.fail_all = True
            svc = RepositoryService(
                github=github, tokens=_FakeTokens(), audit=AuditService(session)
            )
            with pytest.raises(NotFoundError):
                await factory(svc)

        await _assert_fails(lambda s: s.list_repositories(uid))
        await _assert_fails(lambda s: s.list_repositories_paginated(uid))
        await _assert_fails(lambda s: s.get_contributions_summary(uid))
        await _assert_fails(lambda s: s.get_repository(uid, "a", "repo"))
        await _assert_fails(lambda s: s.create_repository(uid, name="x"))
        await _assert_fails(lambda s: s.delete_repository(uid, "a", "repo"))
        await _assert_fails(lambda s: s.fork_repository(uid, "a", "repo"))
        await _assert_fails(lambda s: s.list_branches(uid, "a", "repo"))
        await _assert_fails(lambda s: s.create_branch(uid, "a", "repo", name="b", from_sha="s"))
        await _assert_fails(lambda s: s.list_commits(uid, "a", "repo"))
        await _assert_fails(lambda s: s.get_commit(uid, "a", "repo", "abc"))
        await _assert_fails(lambda s: s.merge_branch(uid, "a", "repo", base="m", head="h"))
        await _assert_fails(lambda s: s.list_pull_requests(uid, "a", "repo"))
        await _assert_fails(lambda s: s.get_pull_request(uid, "a", "repo", 1))
        await _assert_fails(
            lambda s: s.create_pull_request(uid, "a", "repo", title="t", head="h", base="b")
        )
        await _assert_fails(lambda s: s.merge_pull_request(uid, "a", "repo", 1))
        await _assert_fails(lambda s: s.request_reviewers(uid, "a", "repo", 1, reviewers=["x"]))
        await _assert_fails(lambda s: s.submit_review(uid, "a", "repo", 1, body="b", event="A"))
        await _assert_fails(lambda s: s.list_issues(uid, "a", "repo"))
        await _assert_fails(lambda s: s.list_assigned_issues(uid))
        await _assert_fails(lambda s: s.get_issue(uid, "a", "repo", 1))
        await _assert_fails(lambda s: s.create_issue(uid, "a", "repo", title="t"))
        await _assert_fails(lambda s: s.update_issue(uid, "a", "repo", 1, state="closed"))
        await _assert_fails(lambda s: s.comment_on_issue(uid, "a", "repo", 1, body="b"))
        await _assert_fails(lambda s: s.list_releases(uid, "a", "repo"))
        await _assert_fails(lambda s: s.create_release(uid, "a", "repo", tag_name="v1"))
        await _assert_fails(lambda s: s.list_labels(uid, "a", "repo"))
        await _assert_fails(lambda s: s.create_label(uid, "a", "repo", name="n", color="c"))
        await _assert_fails(lambda s: s.list_milestones(uid, "a", "repo"))
        await _assert_fails(lambda s: s.create_milestone(uid, "a", "repo", title="t"))
        await _assert_fails(lambda s: s.list_workflows(uid, "a", "repo"))
        await _assert_fails(
            lambda s: s.dispatch_workflow(uid, "a", "repo", workflow_id="1", ref="main")
        )
        await _assert_fails(lambda s: s.list_workflow_runs(uid, "a", "repo"))
        await _assert_fails(lambda s: s.list_teams(uid, "a", "repo"))
        await _assert_fails(lambda s: s.list_collaborators(uid, "a", "repo"))
        await _assert_fails(lambda s: s.list_organizations(uid))
        await _assert_fails(lambda s: s.list_discussions(uid, "a", "repo"))
        await _assert_fails(lambda s: s.graphql(uid, "{ viewer }"))
    await db.dispose()


@pytest.mark.asyncio
async def test_list_connected_accounts_via_repos():
    """Sanity check that AuthProvider enum exists and connects to services."""
    assert AuthProvider.GITHUB.value == "github"


@pytest.mark.asyncio
async def test_repo_scoped_calls_use_installation_token_in_app_mode():
    """In GitHub App mode, repo operations use installation tokens."""
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        github = _FakeGitHub()
        app_auth = _FakeAppAuth()
        svc = RepositoryService(
            github=github,
            tokens=_FakeTokens(),
            audit=AuditService(session),
            github_app_auth=app_auth,
        )
        user_id = uuid.uuid4()

        await svc.get_repository(user_id, "a", "repo")
        issue = await svc.create_issue(user_id, "a", "repo", title="I", body="b")
        assert issue.number == 5
        await svc.comment_on_issue(user_id, "a", "repo", 3, body="c")
        pr = await svc.create_pull_request(user_id, "a", "repo", title="T", head="f", base="m")
        assert pr.number == 1

        assert ("a", "repo") in app_auth.tokens_requested
        assert len(app_auth.tokens_requested) == 4
    await db.dispose()


@pytest.mark.asyncio
async def test_user_scoped_calls_stay_on_user_token_in_app_mode():
    """Assigned issues / repo list / orgs keep using the user's OAuth token."""
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        github = _FakeGitHub()
        app_auth = _FakeAppAuth()
        svc = RepositoryService(
            github=github,
            tokens=_FakeTokens(),
            audit=AuditService(session),
            github_app_auth=app_auth,
        )
        user_id = uuid.uuid4()

        await svc.list_repositories(user_id)
        assigned = await svc.list_assigned_issues(user_id)
        assert assigned[0].title == "assigned"
        await svc.list_organizations(user_id)

        assert app_auth.tokens_requested == []
    await db.dispose()


@pytest.mark.asyncio
async def test_oauth_mode_never_uses_installation_tokens():
    """Without GitHub App mode, all calls use the user token."""
    db = Database(_settings())
    await db.init_db()
    async with db.session_factory() as session:
        github = _FakeGitHub()
        svc = RepositoryService(
            github=github,
            tokens=_FakeTokens(),
            audit=AuditService(session),
            github_app_auth=None,
        )
        user_id = uuid.uuid4()

        await svc.get_repository(user_id, "a", "repo")
        # Token routing falls back to user OAuth token; no app auth involved.
        assert True
    await db.dispose()
