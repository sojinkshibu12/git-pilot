"use client";

import {
  Activity,
  GitBranch,
  GitCommitHorizontal,
  GitPullRequest,
  Lock,
  Package,
  Settings,
  Star,
  GitFork,
  Eye,
} from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageLoader } from "@/components/ui/spinner";
import { useRepository } from "@/hooks/use-repository";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const TABS = [
  { key: "", label: "Overview", icon: Eye },
  { key: "commits", label: "Commits", icon: GitCommitHorizontal },
  { key: "pulls", label: "Code Review", icon: GitPullRequest },
  { key: "issues", label: "Issues", icon: GitBranch },
  { key: "releases", label: "Releases", icon: Package },
  { key: "actions", label: "Actions", icon: Activity },
  { key: "settings", label: "Settings", icon: Settings },
];

export default function RepositoryLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ owner: string; repo: string }>();
  const pathname = usePathname();
  const owner = params.owner;
  const repo = params.repo;

  const { data: repository, isLoading, isError, error } = useRepository(owner, repo);

  const basePath = `/dashboard/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;
  const activeTab =
    TABS.find(
      (t) =>
        t.key !== "" &&
        (pathname === `${basePath}/${t.key}` || pathname.startsWith(`${basePath}/${t.key}/`)),
    )?.key ?? "";

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/dashboard/repositories"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Repositories
        </Link>

        {isLoading ? (
          <PageLoader />
        ) : isError ? (
          <div className="mt-4 rounded-2xl border border-destructive/20 bg-destructive/5 p-6 text-sm">
            <p className="font-medium">Could not load repository</p>
            <p className="mt-1 text-muted-foreground">
              {error instanceof ApiError
                ? `${error.status} · ${error.code}: ${error.message}`
                : String(error)}
            </p>
            <Button asChild variant="outline" size="sm" className="mt-4">
              <Link href="/dashboard/repositories">Back to repositories</Link>
            </Button>
          </div>
        ) : repository ? (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="truncate text-2xl font-semibold tracking-tight">
                    {repository.full_name}
                  </h1>
                  <Badge variant={repository.private ? "warning" : "success"}>
                    {repository.private ? (
                      <Lock className="h-3 w-3" />
                    ) : (
                      <GitFork className="h-3 w-3" />
                    )}
                    {repository.private ? "Private" : "Public"}
                  </Badge>
                  {repository.language && (
                    <Badge variant="secondary">{repository.language}</Badge>
                  )}
                </div>
                {repository.description && (
                  <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
                    {repository.description}
                  </p>
                )}
              </div>
              <Button asChild variant="outline" size="sm">
                <Link href={repository.html_url} target="_blank" rel="noreferrer">
                  View on GitHub
                </Link>
              </Button>
            </div>

            <div className="flex flex-wrap items-center gap-5 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <Star className="h-4 w-4" /> {repository.stargazers_count.toLocaleString()}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <GitFork className="h-4 w-4" /> {repository.forks_count.toLocaleString()}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <GitBranch className="h-4 w-4" /> {repository.default_branch}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <GitCommitHorizontal className="h-4 w-4" />
                {repository.open_issues_count.toLocaleString()} issues
              </span>
            </div>
          </div>
        ) : null}
      </div>

      <nav className="flex gap-1 overflow-x-auto rounded-xl border bg-card/60 p-1 backdrop-blur">
        {TABS.map(({ key, label, icon: Icon }) => {
          const active = key === activeTab;
          const href = key ? `${basePath}/${key}` : basePath;
          return (
            <Link
              key={key}
              href={href}
              className={cn(
                "inline-flex shrink-0 items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground shadow-md shadow-primary/20"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>

      {children}
    </div>
  );
}
