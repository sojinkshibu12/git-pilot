"""Typed GitHub API models (Pydantic v2).

These are transport models that mirror GitHub's REST/GraphQL payloads. They are
separate from our DB entities (domain models) — the boundary keeps upstream API
churn isolated.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GHBase(BaseModel):
    model_config = ConfigDict(extra="ignore")


class GHUser(GHBase):
    id: int
    login: str
    name: str | None = None
    avatar_url: str | None = None
    html_url: str | None = None
    email: str | None = None
    type: str = "User"
    site_admin: bool = False
    location: str | None = None
    bio: str | None = None
    company: str | None = None
    plan: GHBase | None = None
    followers: int = 0
    following: int = 0
    public_repos: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GHEmail(GHBase):
    email: str
    primary: bool = False
    verified: bool = False
    visibility: str | None = None


class GHAccessToken(GHBase):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    scope: str = ""
    refresh_token: str | None = None
    expires_in: int | None = None
    refresh_token_expires_in: int | None = None
    error: str | None = None
    error_description: str | None = None


class GHOrganization(GHBase):
    id: int
    login: str
    name: str | None = None
    avatar_url: str | None = None
    description: str | None = None
    html_url: str | None = None
    url: str | None = None
    public_members_url: str | None = None
    repos_url: str | None = None
    events_url: str | None = None
    hooks_url: str | None = None
    issues_url: str | None = None
    members_url: str | None = None
    public_repos: int = 0
    total_private_repos: int | None = None
    plan: GHBase | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GHRepository(GHBase):
    id: int
    node_id: str | None = None
    name: str
    full_name: str
    owner: GHUser | dict[str, Any] | None = None
    private: bool = False
    html_url: str
    description: str | None = None
    fork: bool = False
    url: str | None = None
    ssh_url: str | None = None
    clone_url: str | None = None
    git_url: str | None = None
    homepage: str | None = None
    size: int = 0
    stargazers_count: int = 0
    watchers_count: int = 0
    forks_count: int = 0
    open_issues_count: int = 0
    language: str | None = None
    default_branch: str = "main"
    visibility: str = "private"
    topics: list[str] = Field(default_factory=list)
    permissions: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    pushed_at: datetime | None = None


class GHTeam(GHBase):
    id: int
    name: str
    slug: str
    description: str | None = None
    privacy: str | None = None
    permission: str | None = None
    members_url: str | None = None
    repositories_url: str | None = None
    organization: GHOrganization | dict[str, Any] | None = None


class GHCommit(GHBase):
    sha: str
    node_id: str | None = None
    commit: dict[str, Any] | None = None
    message: str | None = None
    url: str | None = None
    author: dict[str, Any] | None = None
    committer: dict[str, Any] | None = None
    parents: list[dict[str, Any]] = Field(default_factory=list)


class GHBranch(GHBase):
    name: str
    commit: dict[str, Any] | None = None
    protected: bool = False


class GHPullRequest(GHBase):
    id: int
    number: int
    state: str
    title: str
    body: str | None = None
    html_url: str
    diff_url: str | None = None
    patch_url: str | None = None
    mergeable: bool | None = None
    merged: bool = False
    mergeable_state: str | None = None
    head: dict[str, Any] | None = None
    base: dict[str, Any] | None = None
    user: GHUser | dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    merged_at: datetime | None = None


class GHIssue(GHBase):
    id: int
    number: int
    state: str
    title: str
    body: str | None = None
    html_url: str
    user: GHUser | dict[str, Any] | None = None
    assignees: list[Any] | None = None
    labels: list[Any] | None = None
    comments: int = 0
    pull_request: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    closed_at: datetime | None = None


class GHComment(GHBase):
    id: int
    body: str
    html_url: str
    user: GHUser | dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GHWorkflowRun(GHBase):
    id: int
    name: str | None = None
    head_branch: str | None = None
    head_sha: str | None = None
    status: str | None = None
    conclusion: str | None = None
    run_number: int = 0
    event: str | None = None
    html_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GHRelease(GHBase):
    id: int
    tag_name: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False
    html_url: str | None = None
    published_at: datetime | None = None


class GHLabels(GHBase):
    id: int
    name: str
    color: str
    description: str | None = None
    default: bool = False


class GHMilestone(GHBase):
    id: int
    number: int
    title: str
    description: str | None = None
    state: str = "open"
    open_issues: int = 0
    closed_issues: int = 0
    created_at: datetime | None = None
    due_on: datetime | None = None


class GHDiscussion(GHBase):
    id: str
    number: int
    title: str
    body: str | None = None
    author: dict[str, Any] | None = None
    category: dict[str, Any] | None = None
    answer_html_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GHPackage(GHBase):
    id: int
    name: str
    package_type: str
    version_count: int = 0
    html_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GHWorkflow(GHBase):
    id: int
    name: str
    path: str
    state: str | None = None
    html_url: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class GHRateLimit(GHBase):
    resources: dict[str, Any] = Field(default_factory=dict)


class GHPaged(GHBase):
    items: list[GHBase]
    next_page: str | None = None
    total_count: int | None = None
    etag: str | None = None
