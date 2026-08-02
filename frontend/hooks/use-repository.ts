"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type {
  AssignedIssuesResponse,
  BranchesResponse,
  CollaboratorsResponse,
  CommitData,
  CommitsResponse,
  IssueData,
  IssuesResponse,
  LabelsResponse,
  MilestonesResponse,
  PullRequestData,
  PullRequestsResponse,
  ReleaseData,
  ReleasesResponse,
  Repository,
  TeamsResponse,
  WorkflowRunsResponse,
  WorkflowsResponse,
} from "@/lib/types";

function repoPath(owner: string, repo: string): string {
  return `/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;
}

export function useRepository(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo],
    queryFn: () => apiFetch<Repository>(repoPath(owner, repo)),
    enabled,
    staleTime: 5 * 60 * 1000,
  });
}

export function useBranches(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "branches"],
    queryFn: () => apiFetch<BranchesResponse>(`${repoPath(owner, repo)}/branches`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useCommits(owner: string, repo: string, sha?: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "commits", sha ?? "default"],
    queryFn: () =>
      apiFetch<CommitsResponse>(
        `${repoPath(owner, repo)}/commits${sha ? `?sha=${encodeURIComponent(sha)}` : ""}`,
      ),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useCommit(owner: string, repo: string, ref: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "commits", ref],
    queryFn: () =>
      apiFetch<CommitData>(
        `${repoPath(owner, repo)}/commits/${encodeURIComponent(ref)}`,
      ),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function usePullRequests(
  owner: string,
  repo: string,
  state: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["repository", owner, repo, "pulls", state],
    queryFn: () =>
      apiFetch<PullRequestsResponse>(
        `${repoPath(owner, repo)}/pulls?state=${encodeURIComponent(state)}`,
      ),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function usePullRequest(
  owner: string,
  repo: string,
  number: number,
  enabled = true,
) {
  return useQuery({
    queryKey: ["repository", owner, repo, "pulls", number],
    queryFn: () => apiFetch<PullRequestData>(`${repoPath(owner, repo)}/pulls/${number}`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useIssues(
  owner: string,
  repo: string,
  state: string,
  enabled = true,
) {
  return useQuery({
    queryKey: ["repository", owner, repo, "issues", state],
    queryFn: () =>
      apiFetch<IssuesResponse>(`${repoPath(owner, repo)}/issues?state=${encodeURIComponent(state)}`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useAssignedIssues(state: string, enabled = true) {
  return useQuery({
    queryKey: ["assigned-issues", state],
    queryFn: () =>
      apiFetch<AssignedIssuesResponse>(`/issues/assigned?state=${encodeURIComponent(state)}`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useIssue(owner: string, repo: string, number: number, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "issues", number],
    queryFn: () => apiFetch<IssueData>(`${repoPath(owner, repo)}/issues/${number}`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useReleases(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "releases"],
    queryFn: () => apiFetch<ReleasesResponse>(`${repoPath(owner, repo)}/releases`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useWorkflowRuns(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "workflow-runs"],
    queryFn: () => apiFetch<WorkflowRunsResponse>(`${repoPath(owner, repo)}/actions/runs`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useWorkflows(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "workflows"],
    queryFn: () => apiFetch<WorkflowsResponse>(`${repoPath(owner, repo)}/workflows`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useLabels(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "labels"],
    queryFn: () => apiFetch<LabelsResponse>(`${repoPath(owner, repo)}/labels`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useMilestones(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "milestones"],
    queryFn: () => apiFetch<MilestonesResponse>(`${repoPath(owner, repo)}/milestones`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useCollaborators(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "collaborators"],
    queryFn: () => apiFetch<CollaboratorsResponse>(`${repoPath(owner, repo)}/collaborators`),
    enabled,
    staleTime: 60 * 1000,
  });
}

export function useTeams(owner: string, repo: string, enabled = true) {
  return useQuery({
    queryKey: ["repository", owner, repo, "teams"],
    queryFn: () => apiFetch<TeamsResponse>(`${repoPath(owner, repo)}/teams`),
    enabled,
    staleTime: 60 * 1000,
  });
}

// ── Mutations ────────────────────────────────────────────────────────────────

interface MutateOptions {
  onSuccess?: () => void;
}

export function useCreatePullRequest(owner: string, repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { title: string; head: string; base: string; body?: string }) =>
      apiFetch(`${repoPath(owner, repo)}/pulls`, {
        method: "POST",
        body: JSON.stringify(payload),
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["repository", owner, repo, "pulls"],
      });
    },
  });
}

export function useMergePullRequest(owner: string, repo: string, number: number, opts: MutateOptions = {}) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (mergeMethod: string) =>
      apiFetch(`${repoPath(owner, repo)}/pulls/${number}/merge`, {
        method: "PUT",
        body: JSON.stringify({ merge_method: mergeMethod }),
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "pulls"] });
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "pulls", number] });
      opts.onSuccess?.();
    },
  });
}

export function useRequestReviewers(owner: string, repo: string, number: number, opts: MutateOptions = {}) {
  return useMutation({
    mutationFn: (reviewers: string[]) =>
      apiFetch(`${repoPath(owner, repo)}/pulls/${number}/reviewers`, {
        method: "POST",
        body: JSON.stringify({ reviewers }),
        csrf: true,
      }),
    onSuccess: opts.onSuccess,
  });
}

export function useSubmitReview(owner: string, repo: string, number: number, opts: MutateOptions = {}) {
  return useMutation({
    mutationFn: (payload: { body: string; event: "APPROVE" | "REQUEST_CHANGES" | "COMMENT" }) =>
      apiFetch(`${repoPath(owner, repo)}/pulls/${number}/reviews`, {
        method: "POST",
        body: JSON.stringify(payload),
        csrf: true,
      }),
    onSuccess: opts.onSuccess,
  });
}

export function useCreateIssue(owner: string, repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { title: string; body?: string }) =>
      apiFetch(`${repoPath(owner, repo)}/issues`, {
        method: "POST",
        body: JSON.stringify(payload),
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "issues"] });
    },
  });
}

export function useCloseIssue(owner: string, repo: string, number: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch(`${repoPath(owner, repo)}/issues/${number}/close`, {
        method: "POST",
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "issues"] });
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "issues", number] });
    },
  });
}

export function useCommentOnIssue(owner: string, repo: string, number: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) =>
      apiFetch(`${repoPath(owner, repo)}/issues/${number}/comments`, {
        method: "POST",
        body: JSON.stringify({ body }),
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "issues", number] });
    },
  });
}

export function useCreateRelease(owner: string, repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { tag_name: string; name?: string; body?: string; draft?: boolean; prerelease?: boolean }) =>
      apiFetch(`${repoPath(owner, repo)}/releases`, {
        method: "POST",
        body: JSON.stringify(payload),
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "releases"] });
    },
  });
}

export function useCreateLabel(owner: string, repo: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { name: string; color: string; description?: string }) =>
      apiFetch(`${repoPath(owner, repo)}/labels`, {
        method: "POST",
        body: JSON.stringify(payload),
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repository", owner, repo, "labels"] });
    },
  });
}

export function useDispatchWorkflow(owner: string, repo: string) {
  return useMutation({
    mutationFn: (payload: { workflow_id: string; ref: string; inputs?: Record<string, string> }) =>
      apiFetch(`${repoPath(owner, repo)}/actions/dispatch`, {
        method: "POST",
        body: JSON.stringify(payload),
        csrf: true,
      }),
  });
}

export function useDeleteRepository(owner: string, repo: string) {
  return useMutation({
    mutationFn: () =>
      apiFetch(repoPath(owner, repo), {
        method: "DELETE",
        csrf: true,
      }),
  });
}

export function useCreateRepository() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      name: string;
      description?: string;
      private?: boolean;
      auto_init?: boolean;
      default_branch?: string;
      has_issues?: boolean;
    }) =>
      apiFetch("/repositories/", {
        method: "POST",
        body: JSON.stringify(payload),
        csrf: true,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["repos"] });
    },
  });
}

export type { ReleaseData };
