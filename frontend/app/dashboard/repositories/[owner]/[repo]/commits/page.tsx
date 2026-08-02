"use client";

import { GitCommitHorizontal, User } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageLoader } from "@/components/ui/spinner";
import { useBranches, useCommits } from "@/hooks/use-repository";
import { cn, commitAuthorDate, formatDateTime, shortSha } from "@/lib/utils";

export default function CommitsPage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = params.owner;
  const repo = params.repo;

  const basePath = `/dashboard/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  const branches = useBranches(owner, repo);
  const defaultBranch = branches.data?.branches[0]?.name ?? "main";
  const [branch, setBranch] = useState<string | null>(null);
  const activeBranch = branch ?? defaultBranch;

  const commits = useCommits(owner, repo, activeBranch === "main" ? "main" : activeBranch);

  const loading = branches.isLoading || (commits.isLoading && !commits.data);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Commit history</h2>
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="font-mono">
            {activeBranch}
          </Badge>
        </div>
      </div>

      {branches.data && branches.data.branches.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          {branches.data.branches.slice(0, 15).map((b) => (
            <button
              key={b.name}
              onClick={() => setBranch(b.name)}
              className={cn(
                "rounded-full border px-2.5 py-1 font-mono text-[11px] transition-colors",
                b.name === activeBranch
                  ? "border-primary/40 bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {b.name}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <PageLoader />
      ) : !commits.data || commits.data.commits.length === 0 ? (
        <EmptyState
          icon={GitCommitHorizontal}
          title="No commits found"
          description={`There are no commits on ${activeBranch} yet.`}
        />
      ) : (
        <Card className="glass-card">
          <CardContent className="p-0">
            <ul className="divide-y">
              {commits.data.commits.map((c) => {
                const message =
                  c.commit?.message?.split("\n")[0] ?? c.message ?? "Commit";
                const body = c.commit?.message?.split("\n").slice(1).join("\n").trim();
                const authorName =
                  (c.author && "login" in c.author && c.author.login) ||
                  c.commit?.author?.name ||
                  "unknown";
                const authorAvatar =
                  c.author && "avatar_url" in c.author && c.author.avatar_url;
                const authorDate = commitAuthorDate(c.commit?.author ?? c.committer);
                return (
                  <li key={c.sha}>
                    <Link
                      href={`${basePath}/commits/${encodeURIComponent(c.sha)}`}
                      className="flex items-start gap-4 p-5 transition-colors hover:bg-accent/40"
                    >
                      {authorAvatar ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={authorAvatar}
                          alt=""
                          className="mt-0.5 h-9 w-9 rounded-full ring-1 ring-border"
                        />
                      ) : (
                        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                          <User className="h-4 w-4" />
                        </div>
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{message}</p>
                        {body && (
                          <p className="mt-0.5 line-clamp-2 whitespace-pre-wrap text-xs text-muted-foreground">
                            {body}
                          </p>
                        )}
                        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
                          <code className="rounded bg-muted px-1.5 py-0.5 font-mono">
                            {shortSha(c.sha)}
                          </code>
                          <span>{authorName}</span>
                          {authorDate && <span>· {formatDateTime(authorDate)}</span>}
                        </div>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
