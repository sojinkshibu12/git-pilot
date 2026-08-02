"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  GitCommitHorizontal,
  GitFork,
  GitPullRequest,
  Star,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ContributionGraph } from "@/components/contributions";
import { GithubBadge } from "@/components/dashboard/shell";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  useContributions,
  useContributionStatistics,
  useContributionStreak,
  useRefreshContributions,
} from "@/hooks/use-contributions";
import { ApiError, apiFetch } from "@/lib/api";
import type { ContributionSummary, RepoListResponse, UserProfile } from "@/lib/types";
import { cn } from "@/lib/utils";

const PER_PAGE = 9;

function Skeletons() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="glass-card space-y-3 p-5">
          <div className="skeleton h-5 w-2/3" />
          <div className="skeleton h-4 w-full" />
          <div className="skeleton h-4 w-1/2" />
        </div>
      ))}
    </div>
  );
}

function pageList(page: number, max: number): (number | "…")[] {
  if (max <= 7) {
    return Array.from({ length: max }, (_, i) => i + 1);
  }
  const wanted = new Set([1, max, page - 1, page, page + 1]);
  const nums = [...wanted].filter((p) => p >= 1 && p <= max).sort((a, b) => a - b);
  const out: (number | "…")[] = [];
  let prev = 0;
  for (const p of nums) {
    if (prev && p - prev > 1) out.push("…");
    out.push(p);
    prev = p;
  }
  return out;
}

function PageControls({
  page,
  totalPages,
  onChange,
}: {
  page: number;
  totalPages: number;
  onChange: (page: number) => void;
}) {
  const pages = pageList(page, totalPages);

  return (
    <div className="flex flex-wrap items-center justify-center gap-1">
      <Button
        variant="ghost"
        size="sm"
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        aria-label="Previous page"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>
      {pages.map((p, i) =>
        p === "…" ? (
          <span key={`e-${i}`} className="px-1 text-sm text-muted-foreground">
            …
          </span>
        ) : (
          <Button
            key={p}
            variant={p === page ? "default" : "ghost"}
            size="sm"
            className="min-w-9"
            onClick={() => onChange(p)}
          >
            {p}
          </Button>
        ),
      )}
      <Button
        variant="ghost"
        size="sm"
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        aria-label="Next page"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </div>
  );
}

export default function DashboardPage() {
  const [page, setPage] = useState(1);
  const [year, setYear] = useState(() => new Date().getFullYear());

  const { data: profile } = useQuery({
    queryKey: ["me"],
    queryFn: () => apiFetch<UserProfile>("/users/me"),
  });

  const { data: contributions } = useQuery({
    queryKey: ["contributions"],
    queryFn: () => apiFetch<ContributionSummary>("/repositories/contributions"),
    enabled: !!profile,
    staleTime: 5 * 60 * 1000,
  });

  const { data: repos, isLoading, isError, isFetching, error: reposError } = useQuery({
    queryKey: ["repos", page],
    queryFn: () =>
      apiFetch<RepoListResponse>(`/repositories/?page=${page}&per_page=${PER_PAGE}`),
    enabled: !!profile,
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });

  const contributionsQuery = useContributions(year, !!profile);
  const contributionReady = !!contributionsQuery.data;
  const streakQuery = useContributionStreak(year, !!profile && contributionReady);
  const statisticsQuery = useContributionStatistics(year, !!profile && contributionReady);
  const refreshMutation = useRefreshContributions(year);

  const stats: { label: string; value: number | string; icon: typeof BookOpen; suffix: string }[] = [
    {
      label: "Repositories",
      value: repos?.total_count ?? 0,
      icon: BookOpen,
      suffix: "total",
    },
    {
      label: "Commits",
      value: contributions?.commits ?? "—",
      icon: GitCommitHorizontal,
      suffix: "this year",
    },
    {
      label: "Pull requests",
      value: contributions?.pull_requests ?? "—",
      icon: GitPullRequest,
      suffix: "this year",
    },
  ];

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Welcome back, {profile?.display_name ?? "there"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {profile?.email ?? "Your GitHub workspace"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {profile?.avatar_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={profile.avatar_url}
              alt=""
              className="h-10 w-10 rounded-full ring-2 ring-border"
            />
          )}
          <GithubBadge login={profile?.email} />
        </div>
      </header>

      <section className="grid gap-4 sm:grid-cols-3">
        {stats.map((s, i) => (
          <motion.div
            key={s.label}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 }}
          >
            <Card className="glass-card">
              <CardContent className="flex items-center justify-between gap-3 p-4">
                <div className="min-w-0">
                  <p className="truncate text-xs text-muted-foreground">{s.label}</p>
                  <p className="mt-0.5 truncate text-xl font-semibold tabular-nums">{s.value}</p>
                  <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{s.suffix}</p>
                </div>
                <div className="shrink-0 rounded-lg bg-primary/10 p-2 text-primary">
                  <s.icon className="h-4 w-4" />
                </div>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </section>

      <section>
        <ContributionGraph
          year={year}
          onYearChange={setYear}
          data={contributionsQuery.data}
          statistics={statisticsQuery.data}
          streak={streakQuery.data}
          isLoading={contributionsQuery.isLoading}
          isRefreshing={refreshMutation.isPending}
          isError={contributionsQuery.isError}
          error={contributionsQuery.error}
          refreshError={refreshMutation.isError ? refreshMutation.error : undefined}
          onRefresh={() => refreshMutation.mutate()}
        />
      </section>

      <section>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Your repositories</h2>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">
              {repos?.total_count ? `${repos.total_count} repos` : ""}
            </span>
            <Link
              href="/dashboard/repositories"
              className="text-sm font-medium text-primary hover:underline"
            >
              View all →
            </Link>
          </div>
        </div>
        {isLoading && <Skeletons />}
        {isError && (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">
              Could not load repositories. Connect a GitHub account to get started.
              {reposError && (
                <p className="mt-2 text-xs text-red-500 dark:text-red-400">
                  {reposError instanceof ApiError
                    ? `${reposError.status} · ${reposError.code}: ${reposError.message}`
                    : String(reposError)}
                </p>
              )}
              <div className="mt-4">
                <Link
                  href="/security/connected-accounts"
                  className="text-primary hover:underline"
                >
                  Connect GitHub →
                </Link>
              </div>
            </CardContent>
          </Card>
        )}
        {repos && (
          <>
            <div
              className={cn(
                "grid gap-4 md:grid-cols-2 transition-opacity",
                isFetching && page > 1 && "opacity-60",
              )}
            >
              {repos.repositories.map((repo, i) => {
                const [owner, name] = repo.full_name.split("/");
                return (
                  <motion.a
                    key={repo.id}
                    href={`/dashboard/repositories/${encodeURIComponent(owner ?? "")}/${encodeURIComponent(name ?? repo.name)}`}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                    className="glass-card group p-5 transition-all hover:-translate-y-1"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="flex items-center gap-2 truncate font-medium">
                          <GitFork className="h-4 w-4 shrink-0 text-muted-foreground" />
                          <span className="truncate group-hover:text-primary">
                            {repo.full_name}
                          </span>
                        </p>
                        <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                          {repo.description ?? "No description provided."}
                        </p>
                      </div>
                      <span
                        className={cn(
                          "shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium",
                          repo.private
                            ? "bg-amber-500/10 text-amber-600 dark:text-amber-400"
                            : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400",
                        )}
                      >
                        {repo.private ? "Private" : "Public"}
                      </span>
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                      <span className="inline-flex items-center gap-1">
                        <Star className="h-3.5 w-3.5" /> {repo.stargazers_count}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <GitFork className="h-3.5 w-3.5" /> {repo.forks_count}
                      </span>
                      {typeof repo.contributions === "number" && (
                        <span
                          className="inline-flex items-center gap-1 text-primary"
                          title="Commits you contributed to this repository"
                        >
                          <GitCommitHorizontal className="h-3.5 w-3.5" />
                          {repo.contributions.toLocaleString()} commits
                        </span>
                      )}
                      {repo.language && (
                        <span className="ml-auto rounded-full bg-muted/60 px-2 py-0.5 font-medium">
                          {repo.language}
                        </span>
                      )}
                    </div>
                  </motion.a>
                );
              })}
            </div>
            {(repos.total_pages > 1 || page > 1) && (
              <div className="mt-6">
                <PageControls
                  page={page}
                  totalPages={Math.max(repos.total_pages, page)}
                  onChange={(p) => {
                    setPage(p);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                />
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
