"use client";

import {
  ArrowLeft,
  FileCode,
  GitCommitHorizontal,
  Plus,
  Minus,
  Copy,
  User,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { PageLoader } from "@/components/ui/spinner";
import { useCommit } from "@/hooks/use-repository";
import {
  cn,
  commitAuthorDate,
  commitAuthorName,
  formatDateTime,
  shortSha,
} from "@/lib/utils";

interface DiffLine {
  kind: "add" | "del" | "ctx" | "hunk";
  text: string;
}

function parsePatch(patch: string | null | undefined): DiffLine[] {
  if (!patch) return [];
  return patch.split("\n").map((line) => {
    if (line.startsWith("+") && !line.startsWith("+++")) {
      return { kind: "add", text: line.slice(1) };
    }
    if (line.startsWith("-") && !line.startsWith("---")) {
      return { kind: "del", text: line.slice(1) };
    }
    if (line.startsWith("@@")) {
      return { kind: "hunk", text: line };
    }
    return { kind: "ctx", text: line };
  });
}

function DiffView({ patch }: { patch: string | null | undefined }) {
  const lines = parsePatch(patch);
  if (lines.length === 0) return null;
  return (
    <pre className="overflow-x-auto rounded-xl bg-muted/60 p-0 font-mono text-[12px] leading-5">
      {lines.map((line, i) => (
        <div
          key={i}
          className={cn(
            "flex gap-3 px-3",
            line.kind === "add" && "bg-emerald-500/10",
            line.kind === "del" && "bg-destructive/10",
            line.kind === "hunk" && "bg-muted font-medium text-primary",
          )}
        >
          <span
            className={cn(
              "w-4 shrink-0 select-none text-center text-muted-foreground/60",
              line.kind === "add" && "text-emerald-500",
              line.kind === "del" && "text-destructive",
            )}
          >
            {line.kind === "add" ? "+" : line.kind === "del" ? "-" : line.kind === "hunk" ? "@" : ""}
          </span>
          <span
            className={cn(
              "whitespace-pre",
              line.kind === "add" && "text-emerald-700 dark:text-emerald-400",
              line.kind === "del" && "text-red-600 dark:text-red-400",
              line.kind === "hunk" && "text-primary",
              line.kind === "ctx" && "text-foreground/80",
            )}
          >
            {line.text}
          </span>
        </div>
      ))}
    </pre>
  );
}

const STATUS_LABELS: Record<string, string> = {
  added: "Added",
  removed: "Removed",
  modified: "Modified",
  renamed: "Renamed",
  copied: "Copied",
  changed: "Changed",
};

export default function CommitDetailPage() {
  const params = useParams<{ owner: string; repo: string; sha: string }>();
  const owner = params.owner;
  const repo = params.repo;
  const ref = params.sha;

  const { data: commit, isLoading, isError, error } = useCommit(owner, repo, ref);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [copied, setCopied] = useState(false);

  const basePath = `/dashboard/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  if (isLoading) return <PageLoader />;

  if (isError || !commit) {
    return (
      <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-6 text-sm">
        <p className="font-medium">Could not load commit</p>
        <p className="mt-1 text-muted-foreground">
          {error instanceof Error ? error.message : String(error)}
        </p>
        <Button asChild variant="outline" size="sm" className="mt-4">
          <Link href={`${basePath}/commits`}>Back to commits</Link>
        </Button>
      </div>
    );
  }

  const message = commit.commit?.message ?? commit.message ?? "Commit";
  const [title, ...rest] = message.split("\n");
  const body = rest.join("\n").trim();

  const authorName = commitAuthorName(commit.author ?? commit.commit?.author);
  const authorDate = commitAuthorDate(commit.commit?.author ?? commit.committer);
  const authorAvatar =
    commit.author && "avatar_url" in commit.author && commit.author.avatar_url;

  const files = commit.files ?? [];
  const totalAdditions = files.reduce((sum, f) => sum + (f.additions ?? 0), 0);
  const totalDeletions = files.reduce((sum, f) => sum + (f.deletions ?? 0), 0);

  const toggleFile = (index: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  const copySha = async () => {
    try {
      await navigator.clipboard.writeText(commit.sha);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard unavailable
    }
  };

  return (
    <div className="space-y-6">
      <Link
        href={`${basePath}/commits`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to commits
      </Link>

      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
            <Badge variant="secondary" className="gap-1 font-mono">
              <GitCommitHorizontal className="h-3 w-3" />
              {shortSha(commit.sha)}
            </Badge>
          </div>
          {body && (
            <p className="mt-2 max-w-3xl whitespace-pre-wrap text-sm text-muted-foreground">
              {body}
            </p>
          )}
          <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            {authorAvatar ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={authorAvatar}
                alt=""
                className="h-5 w-5 rounded-full ring-1 ring-border"
              />
            ) : (
              <User className="h-4 w-4" />
            )}
            <span className="font-medium text-foreground">{authorName}</span>
            {authorDate && <span>· {formatDateTime(authorDate)}</span>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={copySha} className="gap-1.5 font-mono">
            <Copy className="h-3.5 w-3.5" />
            {copied ? "Copied!" : shortSha(commit.sha)}
          </Button>
          {commit.html_url && (
            <Button asChild variant="outline" size="sm">
              <Link href={commit.html_url} target="_blank" rel="noreferrer">
                View on GitHub
              </Link>
            </Button>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Badge variant="success" className="gap-1">
          <Plus className="h-3 w-3" /> {totalAdditions} additions
        </Badge>
        <Badge variant="destructive" className="gap-1">
          <Minus className="h-3 w-3" /> {totalDeletions} deletions
        </Badge>
        <Badge variant="secondary" className="gap-1">
          <FileCode className="h-3 w-3" /> {files.length} file{files.length === 1 ? "" : "s"} changed
        </Badge>
      </div>

      {files.length === 0 ? (
        <EmptyState
          icon={FileCode}
          title="No file changes"
          description="This commit did not change any tracked files."
        />
      ) : (
        <div className="space-y-3">
          {files.map((file, i) => (
            <Card key={`${file.filename}-${i}`} className="glass-card overflow-hidden">
              <button
                onClick={() => toggleFile(i)}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left transition-colors hover:bg-accent/50"
                aria-expanded={expanded.has(i)}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <FileCode className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm">{file.filename}</p>
                    {file.previous_filename && (
                      <p className="text-xs text-muted-foreground">
                        from {file.previous_filename}
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <Badge variant="secondary">{STATUS_LABELS[file.status] ?? file.status}</Badge>
                  <span className="flex items-center gap-2 text-xs tabular-nums">
                    <span className="text-emerald-600 dark:text-emerald-400">
                      +{file.additions}
                    </span>
                    <span className="text-red-600 dark:text-red-400">-{file.deletions}</span>
                  </span>
                </div>
              </button>
              {expanded.has(i) && (
                <div className="border-t">
                  <DiffView patch={file.patch} />
                  {!file.patch && (
                    <p className="px-4 py-3 text-xs text-muted-foreground">
                      No inline diff available for this file.
                    </p>
                  )}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
