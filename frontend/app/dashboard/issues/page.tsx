"use client";

import { Circle, GitPullRequest, Inbox, KeyRound, User } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { GitHubButton } from "@/components/auth/github-button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageLoader } from "@/components/ui/spinner";
import { ApiError } from "@/lib/api";
import { useAssignedIssues } from "@/hooks/use-repository";
import { cn, formatRelativeTime } from "@/lib/utils";

const STATES = ["open", "closed", "all"] as const;

function IssueLabel({ name, color }: { name: string; color?: string }) {
  const bg = color && /^[0-9a-fA-F]{6}$/.test(color) ? `#${color}` : undefined;
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-medium"
      style={
        bg
          ? {
              backgroundColor: `${bg}22`,
              color: bg,
              border: `1px solid ${bg}55`,
            }
          : undefined
      }
    >
      {name}
    </span>
  );
}

export default function AssignedIssuesPage() {
  const [state, setState] = useState<(typeof STATES)[number]>("open");

  const { data, isLoading, isError, error } = useAssignedIssues(state);

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Assigned issues</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Issues assigned to you across all repositories — picked up from
            maintainers or self-assigned.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-lg border bg-muted/40 p-1">
          {STATES.map((s) => (
            <button
              key={s}
              onClick={() => setState(s)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium capitalize transition-colors",
                state === s
                  ? "bg-primary text-primary-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {s}
            </button>
          ))}
        </div>
      </header>

      {isLoading && <PageLoader />}

      {isError && (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Could not load assigned issues.
            {error instanceof ApiError && error.status === 404 ? (
              <div className="mt-3 flex gap-3 rounded-lg border bg-muted/40 p-4">
                <KeyRound className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
                <div className="space-y-3">
                  <div className="space-y-1">
                    <p className="font-medium text-foreground">GitHub token scope needed</p>
                    <p className="text-xs">
                      Listing assigned issues requires read access to your repositories. Re-link
                      your GitHub account to grant the <code className="rounded bg-muted px-1">repo</code>{" "}
                      scope.
                    </p>
                  </div>
                  <div className="w-full max-w-xs">
                    <GitHubButton label="Re-link GitHub account" />
                  </div>
                </div>
              </div>
            ) : (
              error instanceof Error && <p className="mt-2 text-xs text-destructive">{error.message}</p>
            )}
          </CardContent>
        </Card>
      )}

      {data &&
        (data.issues.length === 0 ? (
          <EmptyState
            icon={Inbox}
            title="No assigned issues"
            description={`You have no ${state} issues assigned to you.`}
          />
        ) : (
          <Card className="glass-card">
            <CardContent className="p-0">
              <ul className="divide-y">
                {data.issues.map((issue) => {
                  const repoFull = issue.repository?.full_name ?? issue.repository?.name ?? "unknown";
                  const [owner, repo] = repoFull.split("/");
                  const repoHref = `/dashboard/repositories/${encodeURIComponent(owner ?? "")}/${encodeURIComponent(repo ?? "")}/issues/${issue.number}`;
                  return (
                    <li key={issue.id}>
                      <Link
                        href={repoHref}
                        className="group flex items-start gap-4 p-5 transition-colors hover:bg-accent/40"
                      >
                        {issue.pull_request ? (
                          <GitPullRequest className="mt-1 h-4 w-4 shrink-0 text-emerald-500" />
                        ) : (
                          <Circle
                            className={cn(
                              "mt-1 h-4 w-4 shrink-0",
                              issue.state === "open"
                                ? "fill-emerald-500/20 text-emerald-500"
                                : "fill-muted text-muted-foreground",
                            )}
                          />
                        )}
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-sm font-semibold group-hover:text-primary">
                              {issue.title}
                            </span>
                            {issue.state === "closed" && <Badge variant="secondary">closed</Badge>}
                          </div>
                          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                            <span className="font-mono">{repoFull}</span>
                            <span>·</span>
                            <span>#{issue.number}</span>
                            <span>·</span>
                            <span>opened {formatRelativeTime(issue.created_at)}</span>
                            {issue.comments > 0 && (
                              <>
                                <span>·</span>
                                <span>{issue.comments} comments</span>
                              </>
                            )}
                          </div>
                          <div className="mt-1.5 flex flex-wrap items-center gap-2">
                            {issue.labels && issue.labels.length > 0 && (
                              <span className="flex flex-wrap gap-1">
                                {issue.labels
                                  .filter(
                                    (l): l is { name: string; color?: string } =>
                                      !!l && "name" in l,
                                  )
                                  .slice(0, 5)
                                  .map((l) => (
                                    <IssueLabel key={l.name} name={l.name} color={l.color} />
                                  ))}
                              </span>
                            )}
                            {issue.assignees && issue.assignees.length > 0 && (
                              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                                <User className="h-3 w-3" />
                                {issue.assignees
                                  .filter(
                                    (a): a is { login: string } => !!a && "login" in a,
                                  )
                                  .slice(0, 3)
                                  .map((a) => a.login)
                                  .join(", ")}
                              </span>
                            )}
                          </div>
                        </div>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </CardContent>
          </Card>
        ))}
    </div>
  );
}
