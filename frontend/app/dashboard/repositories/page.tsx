"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  GitFork,
  GitCommitHorizontal,
  Lock,
  Plus,
  Search,
  Star,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageLoader } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useCreateRepository } from "@/hooks/use-repository";
import { ApiError, apiFetch } from "@/lib/api";
import type { RepoListResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const PER_PAGE = 12;

function pageList(page: number, max: number): (number | "…")[] {
  if (max <= 7) return Array.from({ length: max }, (_, i) => i + 1);
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

function CreateRepositoryDialog() {
  const createRepo = useCreateRepository();
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [private_, setPrivate] = useState(true);
  const [autoInit, setAutoInit] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Repository name is required.");
      return;
    }
    if (!/^[\w.-]+$/.test(trimmed)) {
      setError("Name may only contain letters, numbers, hyphens, underscores and dots.");
      return;
    }
    try {
      await createRepo.mutateAsync({
        name: trimmed,
        description: description.trim() || undefined,
        private: private_,
        auto_init: autoInit,
      });
      setOpen(false);
      setName("");
      setDescription("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to create repository.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4" /> New repository
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Create repository</DialogTitle>
          <DialogDescription>A new GitHub repository owned by your account.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="new-repo-name">Name</Label>
            <Input
              id="new-repo-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="my-awesome-project"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="new-repo-desc">Description</Label>
            <Textarea
              id="new-repo-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this repository about?"
              rows={3}
            />
          </div>
          <div className="flex flex-wrap gap-4">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={private_}
                onChange={(e) => setPrivate(e.target.checked)}
                className="h-4 w-4 rounded border-border accent-primary"
              />
              Private
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={autoInit}
                onChange={(e) => setAutoInit(e.target.checked)}
                className="h-4 w-4 rounded border-border accent-primary"
              />
              Initialize with a README
            </label>
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={createRepo.isPending}>
            {createRepo.isPending ? "Creating…" : "Create repository"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function RepositoriesPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const t = setTimeout(() => {
      setDebounced(search.trim());
      setPage(1);
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  const query = debounced || undefined;

  const { data: repos, isLoading, isError, error } = useQuery({
    queryKey: ["repos", page, query ?? ""],
    queryFn: () =>
      apiFetch<RepoListResponse>(
        `/repositories/?page=${page}&per_page=${PER_PAGE}${query ? `&q=${encodeURIComponent(query)}` : ""}`,
      ),
    retry: 1,
    staleTime: 5 * 60 * 1000,
  });

  const showingResults = useMemo(
    () => (repos && query ? repos.total_count : null),
    [repos, query],
  );

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Repositories</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Browse and manage your GitHub repositories.
          </p>
        </div>
        <CreateRepositoryDialog />
      </header>

      <div className="relative max-w-md">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search repositories…"
          className="pl-9 pr-9"
          aria-label="Search repositories"
        />
        {search && (
          <button
            onClick={() => setSearch("")}
            className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-full p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            aria-label="Clear search"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {query && repos && (
        <p className="text-sm text-muted-foreground">
          {repos.repositories.length > 0
            ? `${showingResults} result${showingResults === 1 ? "" : "s"} for “${query}”`
            : `No repositories match “${query}”.`}
        </p>
      )}

      {isLoading && <PageLoader />}

      {isError && (
        <Card>
          <CardContent className="p-6 text-sm text-muted-foreground">
            Could not load repositories.
            {error instanceof ApiError && (
              <p className="mt-2 text-xs text-destructive">
                {error.status} · {error.code}: {error.message}
              </p>
            )}
            <div className="mt-4">
              <Button asChild variant="outline" size="sm">
                <Link href="/security/connected-accounts">Connect GitHub →</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {repos && (
        <>
          {repos.repositories.length === 0 ? (
            query ? (
              <EmptyState
                icon={Search}
                title="No matching repositories"
                description={`No repositories match “${query}”. Try a different search term.`}
              />
            ) : (
              <EmptyState
                icon={BookOpen}
                title="No repositories yet"
                description="Create your first repository to get started."
                action={<CreateRepositoryDialog />}
              />
            )
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {repos.repositories.map((repo, i) => {
                const [owner, name] = repo.full_name.split("/");
                return (
                  <motion.div
                    key={repo.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.04 }}
                  >
                    <Link
                      href={`/dashboard/repositories/${encodeURIComponent(owner ?? "")}/${encodeURIComponent(name ?? repo.name)}`}
                      className="glass-card group block h-full p-5 transition-all hover:-translate-y-1"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <p className="flex items-center gap-2 truncate font-medium">
                            {repo.private ? (
                              <Lock className="h-4 w-4 shrink-0 text-muted-foreground" />
                            ) : (
                              <GitFork className="h-4 w-4 shrink-0 text-muted-foreground" />
                            )}
                            <span className="truncate group-hover:text-primary">
                              {repo.full_name}
                            </span>
                          </p>
                          <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                            {repo.description ?? "No description provided."}
                          </p>
                        </div>
                        <Badge variant={repo.private ? "warning" : "success"}>
                          {repo.private ? "Private" : "Public"}
                        </Badge>
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
                            {repo.contributions.toLocaleString()}
                          </span>
                        )}
                        {repo.language && (
                          <span className="ml-auto rounded-full bg-muted/60 px-2 py-0.5 font-medium">
                            {repo.language}
                          </span>
                        )}
                      </div>
                    </Link>
                  </motion.div>
                );
              })}
            </div>
          )}

          {repos.total_pages > 1 && (
            <div className="mt-6 flex flex-wrap items-center justify-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                aria-label="Previous page"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              {pageList(page, repos.total_pages).map((p, i) =>
                p === "…" ? (
                  <span key={`e-${i}`} className="px-1 text-sm text-muted-foreground">
                    …
                  </span>
                ) : (
                  <Button
                    key={p}
                    variant={p === page ? "default" : "ghost"}
                    size="sm"
                    className={cn("min-w-9")}
                    onClick={() => setPage(p)}
                  >
                    {p}
                  </Button>
                ),
              )}
              <Button
                variant="ghost"
                size="sm"
                disabled={page >= repos.total_pages}
                onClick={() => setPage((p) => p + 1)}
                aria-label="Next page"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
