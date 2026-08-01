"""Repository management endpoints — a secure gateway to the GitHub API.

Every endpoint requires an authenticated session, uses the user's encrypted
GitHub credential server-side, and audits repository access/modification.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.dependencies import (
    AuthenticatedContext,
    CsrfGuard,
    get_authenticated_context,
)
from app.application.dependencies import Services, get_services
from app.schemas import GenericSuccess

router = APIRouter(prefix="/repositories", tags=["repositories"])


class RepoCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    description: str | None = None
    private: bool = True
    auto_init: bool = False
    default_branch: str = "main"
    has_issues: bool = True
    has_projects: bool = True
    has_wiki: bool = True


class PullRequestCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    head: str
    base: str
    body: str | None = None


class IssueCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str | None = None
    labels: list[str] | None = None
    assignees: list[str] | None = None


class CommentCreate(BaseModel):
    body: str = Field(min_length=1)


class BranchCreate(BaseModel):
    name: str = Field(pattern=r"^[\w/.-]+$")
    from_sha: str


class MergeRequest(BaseModel):
    base: str
    head: str
    commit_message: str | None = None


class ReviewerRequest(BaseModel):
    reviewers: list[str] = Field(min_length=1)


class ReviewSubmit(BaseModel):
    body: str | None = None
    event: Literal["APPROVE", "REQUEST_CHANGES", "COMMENT"]


class WorkflowDispatch(BaseModel):
    workflow_id: str
    ref: str
    inputs: dict[str, str] | None = None


class ReleaseCreate(BaseModel):
    tag_name: str
    name: str | None = None
    body: str | None = None
    draft: bool = False
    prerelease: bool = False


class LabelCreate(BaseModel):
    name: str = Field(min_length=1)
    color: str = Field(pattern=r"^[0-9a-fA-F]{6}$")
    description: str | None = None


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1)
    due_on: str | None = None


class GraphQLQuery(BaseModel):
    query: str = Field(min_length=1)
    variables: dict[str, Any] | None = None


# -- Read -------------------------------------------------------------- #
@router.get("/", summary="List repositories (paginated)")
async def list_repositories(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    page: int = Query(1, ge=1),
    per_page: int = Query(9, ge=1, le=100),
) -> dict[str, Any]:
    return await services.repos.list_repositories_paginated(
        context.user.id, page=page, per_page=per_page
    )


@router.get("/contributions", summary="Yearly contribution totals")
async def contributions(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return await services.repos.get_contributions_summary(context.user.id)


@router.get("/{owner}/{repo}", summary="Get repository")
async def get_repository(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> Any:
    return await services.repos.get_repository(context.user.id, owner, repo)


@router.get("/{owner}/{repo}/branches", summary="List branches")
async def list_branches(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"branches": await services.repos.list_branches(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/commits", summary="List commits")
async def list_commits(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    sha: str | None = None,
) -> dict[str, Any]:
    return {"commits": await services.repos.list_commits(context.user.id, owner, repo, sha=sha)}


@router.get("/{owner}/{repo}/pulls", summary="List pull requests")
async def list_pulls(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    state: str = "open",
) -> dict[str, Any]:
    return {
        "pull_requests": await services.repos.list_pull_requests(
            context.user.id, owner, repo, state=state
        )
    }


@router.get("/{owner}/{repo}/pulls/{number}", summary="Get pull request")
async def get_pull(
    owner: str,
    repo: str,
    number: int,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> Any:
    return await services.repos.get_pull_request(context.user.id, owner, repo, number)


@router.get("/{owner}/{repo}/issues", summary="List issues")
async def list_issues(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    state: str = "open",
) -> dict[str, Any]:
    return {"issues": await services.repos.list_issues(context.user.id, owner, repo, state=state)}


@router.get("/{owner}/{repo}/issues/{number}", summary="Get issue")
async def get_issue(
    owner: str,
    repo: str,
    number: int,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> Any:
    return await services.repos.get_issue(context.user.id, owner, repo, number)


@router.get("/{owner}/{repo}/releases", summary="List releases")
async def list_releases(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"releases": await services.repos.list_releases(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/labels", summary="List labels")
async def list_labels(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"labels": await services.repos.list_labels(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/milestones", summary="List milestones")
async def list_milestones(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"milestones": await services.repos.list_milestones(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/workflows", summary="List workflows")
async def list_workflows(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"workflows": await services.repos.list_workflows(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/actions/runs", summary="List workflow runs")
async def list_workflow_runs(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"workflow_runs": await services.repos.list_workflow_runs(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/collaborators", summary="List collaborators")
async def list_collaborators(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"collaborators": await services.repos.list_collaborators(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/teams", summary="List teams")
async def list_teams(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"teams": await services.repos.list_teams(context.user.id, owner, repo)}


@router.get("/{owner}/{repo}/discussions", summary="List discussions (GraphQL)")
async def list_discussions(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"discussions": await services.repos.list_discussions(context.user.id, owner, repo)}


@router.get("/orgs", summary="List organizations")
async def list_orgs(
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
) -> dict[str, Any]:
    return {"organizations": await services.repos.list_organizations(context.user.id)}


# -- Write (CSRF protected) -------------------------------------------- #
@router.post("/", response_model=GenericSuccess, summary="Create repository")
async def create_repository(
    payload: RepoCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    repo = await services.repos.create_repository(context.user.id, **payload.model_dump())
    await services.db.commit()
    return GenericSuccess(detail="Repository created.", data=repo.model_dump())


@router.post("/{owner}/{repo}/forks", response_model=GenericSuccess, summary="Fork repository")
async def fork_repository(
    owner: str,
    repo: str,
    payload: dict[str, Any],
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    forked = await services.repos.fork_repository(
        context.user.id, owner, repo, organization=payload.get("organization")
    )
    await services.db.commit()
    return GenericSuccess(detail="Repository forked.", data=forked.model_dump())


@router.delete("/{owner}/{repo}", response_model=GenericSuccess, summary="Delete repository")
async def delete_repository(
    owner: str,
    repo: str,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    await services.repos.delete_repository(context.user.id, owner, repo)
    await services.db.commit()
    return GenericSuccess(detail="Repository deleted.")


@router.post("/{owner}/{repo}/branches", response_model=GenericSuccess, summary="Create branch")
async def create_branch(
    owner: str,
    repo: str,
    payload: BranchCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    await services.repos.create_branch(
        context.user.id, owner, repo, name=payload.name, from_sha=payload.from_sha
    )
    await services.db.commit()
    return GenericSuccess(detail="Branch created.")


@router.post("/{owner}/{repo}/merges", response_model=GenericSuccess, summary="Merge branches")
async def merge_branches(
    owner: str,
    repo: str,
    payload: MergeRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    result = await services.repos.merge_branch(
        context.user.id, owner, repo, base=payload.base, head=payload.head
    )
    await services.db.commit()
    return GenericSuccess(detail="Branches merged.", data=result.model_dump())


@router.post("/{owner}/{repo}/pulls", response_model=GenericSuccess, summary="Create pull request")
async def create_pull(
    owner: str,
    repo: str,
    payload: PullRequestCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    pr = await services.repos.create_pull_request(
        context.user.id,
        owner,
        repo,
        title=payload.title,
        head=payload.head,
        base=payload.base,
        body=payload.body,
    )
    await services.db.commit()
    return GenericSuccess(detail="Pull request created.", data=pr.model_dump())


@router.put(
    "/{owner}/{repo}/pulls/{number}/merge",
    response_model=GenericSuccess,
    summary="Merge pull request",
)
async def merge_pull(
    owner: str,
    repo: str,
    number: int,
    payload: dict[str, Any],
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    result = await services.repos.merge_pull_request(
        context.user.id, owner, repo, number, merge_method=payload.get("merge_method", "merge")
    )
    await services.db.commit()
    return GenericSuccess(detail="Pull request merged.", data=result.model_dump())


@router.post(
    "/{owner}/{repo}/pulls/{number}/reviewers",
    response_model=GenericSuccess,
    summary="Request reviewers",
)
async def request_reviewers(
    owner: str,
    repo: str,
    number: int,
    payload: ReviewerRequest,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    await services.repos.request_reviewers(
        context.user.id, owner, repo, number, reviewers=payload.reviewers
    )
    await services.db.commit()
    return GenericSuccess(detail="Reviewers requested.")


@router.post(
    "/{owner}/{repo}/pulls/{number}/reviews",
    response_model=GenericSuccess,
    summary="Submit a review",
)
async def submit_review(
    owner: str,
    repo: str,
    number: int,
    payload: ReviewSubmit,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    result = await services.repos.submit_review(
        context.user.id, owner, repo, number, body=payload.body or "", event=payload.event
    )
    await services.db.commit()
    return GenericSuccess(detail="Review submitted.", data=result)


@router.post("/{owner}/{repo}/issues", response_model=GenericSuccess, summary="Create issue")
async def create_issue(
    owner: str,
    repo: str,
    payload: IssueCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    issue = await services.repos.create_issue(
        context.user.id, owner, repo, title=payload.title, body=payload.body
    )
    await services.db.commit()
    return GenericSuccess(detail="Issue created.", data=issue.model_dump())


@router.patch(
    "/{owner}/{repo}/issues/{number}", response_model=GenericSuccess, summary="Update issue"
)
async def update_issue(
    owner: str,
    repo: str,
    number: int,
    payload: dict[str, Any],
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    issue = await services.repos.update_issue(context.user.id, owner, repo, number, **payload)
    await services.db.commit()
    return GenericSuccess(detail="Issue updated.", data=issue.model_dump())


@router.post(
    "/{owner}/{repo}/issues/{number}/close", response_model=GenericSuccess, summary="Close issue"
)
async def close_issue(
    owner: str,
    repo: str,
    number: int,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    issue = await services.repos.close_issue(context.user.id, owner, repo, number)
    await services.db.commit()
    return GenericSuccess(detail="Issue closed.", data=issue.model_dump())


@router.post(
    "/{owner}/{repo}/issues/{number}/comments",
    response_model=GenericSuccess,
    summary="Comment on issue",
)
async def comment_on_issue(
    owner: str,
    repo: str,
    number: int,
    payload: CommentCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    comment = await services.repos.comment_on_issue(
        context.user.id, owner, repo, number, body=payload.body
    )
    await services.db.commit()
    return GenericSuccess(detail="Comment added.", data=comment.model_dump())


@router.post("/{owner}/{repo}/releases", response_model=GenericSuccess, summary="Create release")
async def create_release(
    owner: str,
    repo: str,
    payload: ReleaseCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    rel = await services.repos.create_release(
        context.user.id, owner, repo, **payload.model_dump(exclude_none=True)
    )
    await services.db.commit()
    return GenericSuccess(detail="Release created.", data=rel.model_dump())


@router.post("/{owner}/{repo}/labels", response_model=GenericSuccess, summary="Create label")
async def create_label(
    owner: str,
    repo: str,
    payload: LabelCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    label = await services.repos.create_label(
        context.user.id,
        owner,
        repo,
        name=payload.name,
        color=payload.color,
        description=payload.description,
    )
    await services.db.commit()
    return GenericSuccess(detail="Label created.", data=label.model_dump())


@router.post(
    "/{owner}/{repo}/milestones", response_model=GenericSuccess, summary="Create milestone"
)
async def create_milestone(
    owner: str,
    repo: str,
    payload: MilestoneCreate,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    ms = await services.repos.create_milestone(
        context.user.id, owner, repo, title=payload.title, due_on=payload.due_on
    )
    await services.db.commit()
    return GenericSuccess(detail="Milestone created.", data=ms.model_dump())


@router.post(
    "/{owner}/{repo}/actions/dispatch",
    response_model=GenericSuccess,
    summary="Trigger GitHub Actions workflow",
)
async def dispatch_workflow(
    owner: str,
    repo: str,
    payload: WorkflowDispatch,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> GenericSuccess:
    await services.repos.dispatch_workflow(
        context.user.id,
        owner,
        repo,
        workflow_id=payload.workflow_id,
        ref=payload.ref,
        inputs=payload.inputs,
    )
    await services.db.commit()
    return GenericSuccess(detail="Workflow dispatched.")


@router.post("/graphql", summary="Execute arbitrary GraphQL against GitHub")
async def graphql(
    payload: GraphQLQuery,
    context: Annotated[AuthenticatedContext, Depends(get_authenticated_context)],
    services: Annotated[Services, Depends(get_services)],
    _csrf: CsrfGuard = None,
) -> dict[str, Any]:
    data = await services.repos.graphql(context.user.id, payload.query, payload.variables)
    await services.db.commit()
    return {"data": data}
