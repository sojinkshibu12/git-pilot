"""Repository service — secure gateway to GitHub repo/PR/issue/actions APIs.

Every mutation is authorized (token scopes) and audited. Responses are typed
via the GitHub client's Pydantic models.
"""

from __future__ import annotations

import asyncio
import math
import uuid
from typing import Any

from app.application.services.audit_service import AuditService
from app.application.services.token_service import TokenService
from app.core.logging import get_logger
from app.domain.models.enums import AuditEventType
from app.infrastructure.github.client import GitHubAPIClient
from app.infrastructure.github.exceptions import GitHubClientError, to_domain_exception

logger = get_logger("repos")


class RepositoryService:
    def __init__(
        self, *, github: GitHubAPIClient, tokens: TokenService, audit: AuditService
    ) -> None:
        self._github = github
        self._tokens = tokens
        self._audit = audit

    async def _token_for(self, user_id: uuid.UUID) -> str:
        return await self._tokens.access_token_for_user(user_id)

    async def _audit_repo(
        self,
        user_id: uuid.UUID,
        action: str,
        *,
        outcome: str = "success",
        resource: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        await self._audit.record(
            AuditEventType.REPOSITORY_MODIFICATION
            if "modify" in action
            else AuditEventType.REPOSITORY_ACCESS,
            user_id=user_id,
            action=action,
            resource_type="repository",
            resource_id=resource,
            metadata=extra,
        )

    # -- Read side ------------------------------------------------------ #
    async def list_repositories(self, user_id: uuid.UUID) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            repos = await self._github.list_repositories(token)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(user_id, "repository.access.list", resource="repos")
        return repos

    async def list_repositories_paginated(
        self, user_id: uuid.UUID, *, page: int = 1, per_page: int = 9
    ) -> dict[str, Any]:
        """Paginated repository list, each repo annotated with the user's commit
        contribution count (GitHub-style "commits contributed")."""
        token = await self._token_for(user_id)
        login = await self._tokens.github_login_for_user(user_id)
        try:
            paged = await self._github.list_repositories_page(token, page=page, per_page=per_page)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

        repos = [repo.model_dump(mode="json") for repo in paged.items]
        if login:
            counts = await self._commit_counts(token, login, paged.items)
            for repo in repos:
                repo_id = repo.get("id")
                repo["contributions"] = counts.get(repo_id) if isinstance(repo_id, int) else None
        else:
            for repo in repos:
                repo["contributions"] = None

        total = paged.total_count or len(repos)
        await self._audit_repo(user_id, "repository.access.list", resource="repos")
        return {
            "repositories": repos,
            "page": page,
            "per_page": per_page,
            "total_count": total,
            "total_pages": max(1, math.ceil(total / per_page)) if total else 0,
        }

    async def get_contributions_summary(self, user_id: uuid.UUID) -> dict[str, int]:
        """Yearly contribution totals (commits, PRs, issues, reviews)."""
        token = await self._token_for(user_id)
        login = await self._tokens.github_login_for_user(user_id)
        if not login:
            return {"commits": 0, "pull_requests": 0, "issues": 0, "reviews": 0, "total": 0}
        try:
            return await self._github.get_contributions_summary(token, login)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def _commit_counts(self, token: str, login: str, repos: list[Any]) -> dict[int, int]:
        """Concurrent, bounded commit-count lookups (per_page=1 + Link trick)."""
        semaphore = asyncio.Semaphore(5)

        async def _one(repo: Any) -> tuple[int, int]:
            owner = (repo.full_name or repo.name).split("/")[0]
            try:
                async with semaphore:
                    count = await self._github.get_commit_count_for_user(
                        token, owner, repo.name, author=login
                    )
            except GitHubClientError:
                count = 0
            return repo.id, count

        results = await asyncio.gather(*(_one(repo) for repo in repos))
        return dict(results)

    async def get_repository(self, user_id: uuid.UUID, owner: str, repo: str) -> Any:
        token = await self._token_for(user_id)
        try:
            result = await self._github.get_repository(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(user_id, "repository.access.read", resource=f"{owner}/{repo}")
        return result

    # -- Write side ----------------------------------------------------- #
    async def create_repository(self, user_id: uuid.UUID, **payload: Any) -> Any:
        token = await self._token_for(user_id)
        try:
            repo = await self._github.create_repository(token, **payload)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id, "repository.modify.create", resource=repo.full_name, extra={"name": repo.name}
        )
        return repo

    async def delete_repository(self, user_id: uuid.UUID, owner: str, repo: str) -> None:
        token = await self._token_for(user_id)
        try:
            await self._github.delete_repository(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(user_id, "repository.modify.delete", resource=f"{owner}/{repo}")

    async def fork_repository(
        self, user_id: uuid.UUID, owner: str, repo: str, *, organization: str | None = None
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            forked = await self._github.fork_repository(
                token, owner, repo, organization=organization
            )
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(user_id, "repository.modify.fork", resource=f"{owner}/{repo}")
        return forked

    # -- Branches / commits -------------------------------------------- #
    async def list_branches(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_branches(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def create_branch(
        self, user_id: uuid.UUID, owner: str, repo: str, *, name: str, from_sha: str
    ) -> None:
        token = await self._token_for(user_id)
        try:
            await self._github.create_branch(token, owner, repo, name=name, from_sha=from_sha)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.create_branch",
            resource=f"{owner}/{repo}",
            extra={"branch": name},
        )

    async def list_commits(
        self, user_id: uuid.UUID, owner: str, repo: str, *, sha: str | None = None
    ) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_commits(token, owner, repo, sha=sha)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def merge_branch(
        self, user_id: uuid.UUID, owner: str, repo: str, *, base: str, head: str
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            merged = await self._github.merge_branch(token, owner, repo, base=base, head=head)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.merge_branch",
            resource=f"{owner}/{repo}",
            extra={"base": base, "head": head},
        )
        return merged

    # -- Pull requests -------------------------------------------------- #
    async def list_pull_requests(
        self, user_id: uuid.UUID, owner: str, repo: str, *, state: str = "open"
    ) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_pull_requests(token, owner, repo, state=state)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def get_pull_request(self, user_id: uuid.UUID, owner: str, repo: str, number: int) -> Any:
        token = await self._token_for(user_id)
        try:
            return await self._github.get_pull_request(token, owner, repo, number)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def create_pull_request(
        self,
        user_id: uuid.UUID,
        owner: str,
        repo: str,
        *,
        title: str,
        head: str,
        base: str,
        body: str | None = None,
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            pr = await self._github.create_pull_request(
                token, owner, repo, title=title, head=head, base=base, body=body
            )
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.create_pr",
            resource=f"{owner}/{repo}",
            extra={"pr": pr.number},
        )
        return pr

    async def merge_pull_request(
        self, user_id: uuid.UUID, owner: str, repo: str, number: int, *, merge_method: str = "merge"
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            pr = await self._github.merge_pull_request(
                token, owner, repo, number, merge_method=merge_method
            )
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id, "repository.modify.merge_pr", resource=f"{owner}/{repo}", extra={"pr": number}
        )
        return pr

    async def request_reviewers(
        self, user_id: uuid.UUID, owner: str, repo: str, number: int, *, reviewers: list[str]
    ) -> None:
        token = await self._token_for(user_id)
        try:
            await self._github.request_reviewers(token, owner, repo, number, reviewers=reviewers)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.request_reviewers",
            resource=f"{owner}/{repo}",
            extra={"pr": number, "reviewers": reviewers},
        )

    async def submit_review(
        self, user_id: uuid.UUID, owner: str, repo: str, number: int, *, body: str, event: str
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            return await self._github.submit_review(
                token, owner, repo, number, body=body, event=event
            )
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    # -- Issues --------------------------------------------------------- #
    async def list_issues(
        self, user_id: uuid.UUID, owner: str, repo: str, *, state: str = "open"
    ) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_issues(token, owner, repo, state=state)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def get_issue(self, user_id: uuid.UUID, owner: str, repo: str, number: int) -> Any:
        token = await self._token_for(user_id)
        try:
            return await self._github.get_issue(token, owner, repo, number)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def create_issue(
        self, user_id: uuid.UUID, owner: str, repo: str, *, title: str, body: str | None = None
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            issue = await self._github.create_issue(token, owner, repo, title=title, body=body)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.create_issue",
            resource=f"{owner}/{repo}",
            extra={"issue": issue.number},
        )
        return issue

    async def update_issue(
        self, user_id: uuid.UUID, owner: str, repo: str, number: int, **fields: Any
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            issue = await self._github.update_issue(token, owner, repo, number, **fields)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.update_issue",
            resource=f"{owner}/{repo}",
            extra={"issue": number},
        )
        return issue

    async def close_issue(self, user_id: uuid.UUID, owner: str, repo: str, number: int) -> Any:
        return await self.update_issue(user_id, owner, repo, number, state="closed")

    async def comment_on_issue(
        self, user_id: uuid.UUID, owner: str, repo: str, number: int, *, body: str
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            return await self._github.comment_on_issue(token, owner, repo, number, body=body)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    # -- Releases / labels / milestones --------------------------------- #
    async def list_releases(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_releases(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def create_release(
        self, user_id: uuid.UUID, owner: str, repo: str, **payload: Any
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            rel = await self._github.create_release(token, owner, repo, **payload)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.create_release",
            resource=f"{owner}/{repo}",
            extra={"tag": rel.tag_name},
        )
        return rel

    async def list_labels(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_labels(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def create_label(
        self,
        user_id: uuid.UUID,
        owner: str,
        repo: str,
        *,
        name: str,
        color: str,
        description: str | None = None,
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            return await self._github.create_label(
                token, owner, repo, name=name, color=color, description=description
            )
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def list_milestones(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_milestones(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def create_milestone(
        self, user_id: uuid.UUID, owner: str, repo: str, *, title: str, due_on: str | None = None
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            return await self._github.create_milestone(
                token, owner, repo, title=title, due_on=due_on
            )
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    # -- Actions / workflows -------------------------------------------- #
    async def list_workflows(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_workflows(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def dispatch_workflow(
        self,
        user_id: uuid.UUID,
        owner: str,
        repo: str,
        *,
        workflow_id: str,
        ref: str,
        inputs: dict[str, Any] | None = None,
    ) -> None:
        token = await self._token_for(user_id)
        try:
            await self._github.dispatch_workflow(
                token, owner, repo, workflow_id=workflow_id, ref=ref, inputs=inputs
            )
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
        await self._audit_repo(
            user_id,
            "repository.modify.dispatch_workflow",
            resource=f"{owner}/{repo}",
            extra={"workflow": workflow_id, "ref": ref},
        )

    async def list_workflow_runs(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_workflow_runs(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    # -- Teams / collaborators / packages / discussions ----------------- #
    async def list_teams(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_teams(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def list_collaborators(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_collaborators(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def list_organizations(self, user_id: uuid.UUID) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_organizations(token)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def list_discussions(self, user_id: uuid.UUID, owner: str, repo: str) -> list[Any]:
        token = await self._token_for(user_id)
        try:
            return await self._github.list_discussions(token, owner, repo)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc

    async def graphql(
        self, user_id: uuid.UUID, query: str, variables: dict[str, Any] | None = None
    ) -> Any:
        token = await self._token_for(user_id)
        try:
            return await self._github.graphql(token, query, variables)
        except GitHubClientError as exc:
            raise to_domain_exception(exc) from exc
