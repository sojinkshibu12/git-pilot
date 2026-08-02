"use client";

import {
  ArrowLeft,
  CheckCircle2,
  GitMerge,
  MessageSquare,
  ThumbsUp,
  XCircle,
  User,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageLoader } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import {
  useMergePullRequest,
  usePullRequest,
  useRequestReviewers,
  useSubmitReview,
} from "@/hooks/use-repository";
import { formatDateTime, formatRelativeTime, shortSha } from "@/lib/utils";
import { cn } from "@/lib/utils";

function StateBadge({ pr }: { pr: { state: string; merged: boolean } }) {
  if (pr.merged) return <Badge variant="info">Merged</Badge>;
  if (pr.state === "closed") return <Badge variant="destructive">Closed</Badge>;
  return <Badge variant="success">Open</Badge>;
}

export default function PullRequestDetailPage() {
  const params = useParams<{ owner: string; repo: string; number: string }>();
  const router = useRouter();
  const owner = params.owner;
  const repo = params.repo;
  const number = Number(params.number);

  const { data: pr, isLoading, isError, error } = usePullRequest(owner, repo, number);
  const mergeMutation = useMergePullRequest(owner, repo, number);
  const reviewMutation = useSubmitReview(owner, repo, number);
  const reviewersMutation = useRequestReviewers(owner, repo, number);

  const [reviewBody, setReviewBody] = useState("");
  const [reviewEvent, setReviewEvent] = useState<"APPROVE" | "REQUEST_CHANGES" | "COMMENT">("COMMENT");
  const [reviewers, setReviewers] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const basePath = `/dashboard/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  if (isLoading) return <PageLoader />;

  if (isError || !pr) {
    return (
      <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-6 text-sm">
        <p className="font-medium">Could not load pull request</p>
        <p className="mt-1 text-muted-foreground">
          {error instanceof Error ? error.message : String(error)}
        </p>
      </div>
    );
  }

  const handleMerge = async () => {
    setActionError(null);
    try {
      await mergeMutation.mutateAsync("merge");
      router.refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to merge.");
    }
  };

  const handleReview = async () => {
    setActionError(null);
    if (!reviewBody.trim()) {
      setActionError("A review requires a comment.");
      return;
    }
    try {
      await reviewMutation.mutateAsync({ body: reviewBody, event: reviewEvent });
      setReviewBody("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to submit review.");
    }
  };

  const handleRequestReviewers = async () => {
    setActionError(null);
    const list = reviewers
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (list.length === 0) {
      setActionError("Enter at least one reviewer login.");
      return;
    }
    try {
      await reviewersMutation.mutateAsync(list);
      setReviewers("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to request reviewers.");
    }
  };

  return (
    <div className="space-y-6">
      <Link
        href={`${basePath}/pulls`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to pull requests
      </Link>

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">#{pr.number}</h2>
          <StateBadge pr={pr} />
          {pr.mergeable === false && <Badge variant="destructive">Merge conflicts</Badge>}
        </div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{pr.title}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <User className="h-4 w-4" />
            {pr.user && "login" in pr.user ? pr.user.login : "unknown"}
          </span>
          <span>
            opened {formatRelativeTime(pr.created_at)} · updated {formatRelativeTime(pr.updated_at)}
          </span>
          {pr.merged_at && <span>merged {formatDateTime(pr.merged_at)}</span>}
        </p>
        <p className="mt-3 inline-flex items-center gap-2 rounded-lg bg-muted px-3 py-1.5 font-mono text-xs">
          <span>{pr.base?.ref}</span>
          <ArrowLeft className="h-3.5 w-3.5 rotate-180" />
          <span>{pr.head?.ref}</span>
          {pr.head?.sha && <span className="text-muted-foreground">{shortSha(pr.head.sha)}</span>}
        </p>
      </div>

      {pr.body && (
        <Card className="glass-card">
          <CardContent className="whitespace-pre-wrap p-5 text-sm leading-relaxed">
            {pr.body}
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={handleMerge}
          disabled={mergeMutation.isPending || pr.merged || pr.state === "closed"}
          className="gap-2"
        >
          <GitMerge className="h-4 w-4" />
          {mergeMutation.isPending
            ? "Merging…"
            : pr.merged
              ? "Merged"
              : `Merge into ${pr.base?.ref}`}
        </Button>
        {pr.html_url && (
          <Button asChild variant="outline">
            <Link href={pr.html_url} target="_blank" rel="noreferrer">
              View diff on GitHub
            </Link>
          </Button>
        )}
      </div>

      {actionError && (
        <p className="text-sm text-destructive" role="alert">
          {actionError}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ThumbsUp className="h-4 w-4 text-primary" /> Submit review
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-1.5">
              {(
                [
                  { value: "APPROVE", label: "Approve", icon: CheckCircle2 },
                  { value: "REQUEST_CHANGES", label: "Request changes", icon: XCircle },
                  { value: "COMMENT", label: "Comment", icon: MessageSquare },
                ] as const
              ).map(({ value, label, icon: Icon }) => (
                <button
                  key={value}
                  onClick={() => setReviewEvent(value)}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors",
                    reviewEvent === value
                      ? "border-primary/40 bg-primary/10 text-primary"
                      : "border-border text-muted-foreground hover:bg-accent",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {label}
                </button>
              ))}
            </div>
            <Textarea
              value={reviewBody}
              onChange={(e) => setReviewBody(e.target.value)}
              placeholder="Leave a review comment…"
            />
            <Button onClick={handleReview} disabled={reviewMutation.isPending}>
              {reviewMutation.isPending ? "Submitting…" : "Submit review"}
            </Button>
          </CardContent>
        </Card>

        <Card className="glass-card">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <User className="h-4 w-4 text-primary" /> Request reviewers
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Enter GitHub usernames, comma-separated.
            </p>
            <Textarea
              value={reviewers}
              onChange={(e) => setReviewers(e.target.value)}
              placeholder="octocat, hubot"
              rows={2}
            />
            <Button
              variant="outline"
              onClick={handleRequestReviewers}
              disabled={reviewersMutation.isPending}
            >
              {reviewersMutation.isPending ? "Requesting…" : "Request reviewers"}
            </Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
