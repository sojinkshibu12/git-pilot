"use client";

import {
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  GitFork,
  GitMerge,
  User,
  Star,
} from "lucide-react";
import { useParams } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageLoader } from "@/components/ui/spinner";
import { useBranches, useCommits, useIssues, usePullRequests } from "@/hooks/use-repository";
import { commitAuthorDate, shortSha } from "@/lib/utils";

function CommitRow({
  sha,
  message,
  author,
  date,
}: {
  sha: string;
  message: string;
  author: string;
  date: string;
}) {
  return (
    <li className="flex items-start gap-3 py-3">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <GitCommitHorizontal className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium">{message || "—"}</p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          <code className="rounded bg-muted px-1 py-0.5 font-mono">{shortSha(sha)}</code>
          <span className="mx-1">·</span>
          {author}
        </p>
      </div>
      <span className="shrink-0 text-xs text-muted-foreground">{date}</span>
    </li>
  );
}

export default function RepositoryOverviewPage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = params.owner;
  const repo = params.repo;

  const branches = useBranches(owner, repo);
  const commits = useCommits(owner, repo, "main");
  const pulls = usePullRequests(owner, repo, "open");
  const issues = useIssues(owner, repo, "open");

  const loading = branches.isLoading || commits.isLoading || pulls.isLoading || issues.isLoading;

  if (loading) return <PageLoader />;

  const stats = [
    {
      label: "Open pull requests",
      value: pulls.data?.pull_requests.length ?? 0,
      icon: GitPullRequest,
    },
    {
      label: "Open issues",
      value: issues.data?.issues.length ?? 0,
      icon: GitFork,
    },
    {
      label: "Branches",
      value: branches.data?.branches.length ?? 0,
      icon: GitBranch,
    },
    {
      label: "Recent commits",
      value: commits.data?.commits.length ?? 0,
      icon: GitCommitHorizontal,
    },
  ];

  return (
    <div className="space-y-6">
      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((s) => (
          <Card key={s.label} className="glass-card">
            <CardContent className="flex items-center justify-between gap-3 p-4">
              <div>
                <p className="truncate text-xs text-muted-foreground">{s.label}</p>
                <p className="mt-0.5 text-xl font-semibold tabular-nums">{s.value}</p>
              </div>
              <div className="rounded-lg bg-primary/10 p-2 text-primary">
                <s.icon className="h-4 w-4" />
              </div>
            </CardContent>
          </Card>
        ))}
      </section>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card className="glass-card">
            <CardHeader className="flex-row items-center justify-between space-y-0">
              <CardTitle className="text-base">Recent commits</CardTitle>
              <Badge variant="secondary">{branches.data?.branches[0]?.name ?? "main"}</Badge>
            </CardHeader>
            <CardContent>
              {!commits.data || commits.data.commits.length === 0 ? (
                <EmptyState
                  icon={GitCommitHorizontal}
                  title="No commits found"
                  description="There are no commits on this branch yet."
                />
              ) : (
                <ul className="divide-y">
                  {commits.data.commits.slice(0, 8).map((c) => {
                    const author =
                      (c.author && "login" in c.author && c.author.login) ||
                      c.commit?.author?.name ||
                      "unknown";
                    const date = commitAuthorDate(c.commit?.author ?? c.committer);
                    return (
                      <CommitRow
                        key={c.sha}
                        sha={c.sha}
                        message={
                          c.commit?.message?.split("\n")[0] ??
                          c.message ??
                          c.commit?.message ??
                          "—"
                        }
                        author={String(author)}
                        date={
                          date
                            ? new Date(date).toLocaleDateString(undefined, {
                                month: "short",
                                day: "numeric",
                              })
                            : "—"
                        }
                      />
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="text-base">Branches</CardTitle>
            </CardHeader>
            <CardContent>
              {!branches.data || branches.data.branches.length === 0 ? (
                <EmptyState icon={GitBranch} title="No branches" />
              ) : (
                <ul className="space-y-2">
                  {branches.data.branches.slice(0, 10).map((b) => (
                    <li key={b.name} className="flex items-center gap-2 text-sm">
                      <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="truncate font-mono">{b.name}</span>
                      {b.protected && <Badge variant="info">protected</Badge>}
                      {b.name === "main" && <Badge variant="secondary">default</Badge>}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="text-base">Open pull requests</CardTitle>
            </CardHeader>
            <CardContent>
              {!pulls.data || pulls.data.pull_requests.length === 0 ? (
                <EmptyState
                  icon={GitMerge}
                  title="No open pull requests"
                  description="When collaborators open PRs they'll show up here."
                />
              ) : (
                <ul className="space-y-3">
                  {pulls.data.pull_requests.slice(0, 5).map((pr) => (
                    <li key={pr.id}>
                      <a
                        href={pr.html_url}
                        target="_blank"
                        rel="noreferrer"
                        className="group block text-sm hover:text-primary"
                      >
                        <span className="font-medium">
                          #{pr.number} {pr.title}
                        </span>
                        <span className="mt-0.5 flex items-center gap-1 text-xs text-muted-foreground">
                          <User className="h-3 w-3" />
                          {pr.user && "login" in pr.user ? pr.user.login : "unknown"}
                          <span>·</span>
                          <GitMerge className="h-3 w-3" />
                          {pr.base?.ref} ← {pr.head?.ref}
                        </span>
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card className="glass-card">
            <CardHeader>
              <CardTitle className="text-base">Open issues</CardTitle>
            </CardHeader>
            <CardContent>
              {!issues.data || issues.data.issues.length === 0 ? (
                <EmptyState icon={Star} title="No open issues" />
              ) : (
                <ul className="space-y-3">
                  {issues.data.issues.slice(0, 5).map((issue) => (
                    <li key={issue.id} className="flex items-start gap-2 text-sm">
                      <GitFork className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <div className="min-w-0">
                        <p className="truncate">
                          <span className="text-muted-foreground">#{issue.number}</span>{" "}
                          <span className="font-medium">{issue.title}</span>
                        </p>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          {(issue.labels ?? [])
                            .filter((l): l is { name: string; color?: string } => !!l && "name" in l)
                            .slice(0, 3)
                            .map((l) => (
                              <Badge
                                key={l.name}
                                variant="secondary"
                                className="text-[10px]"
                              >
                                {l.name}
                              </Badge>
                            ))}
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
