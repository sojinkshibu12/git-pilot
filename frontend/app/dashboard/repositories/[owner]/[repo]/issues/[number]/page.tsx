"use client";

import { ArrowLeft, Circle, MessageSquare, Send, User } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageLoader } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { useCloseIssue, useCommentOnIssue, useIssue } from "@/hooks/use-repository";
import { formatRelativeTime } from "@/lib/utils";

export default function IssueDetailPage() {
  const params = useParams<{ owner: string; repo: string; number: string }>();
  const router = useRouter();
  const owner = params.owner;
  const repo = params.repo;
  const number = Number(params.number);

  const { data: issue, isLoading, isError, error } = useIssue(owner, repo, number);
  const closeMutation = useCloseIssue(owner, repo, number);
  const commentMutation = useCommentOnIssue(owner, repo, number);

  const [comment, setComment] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const basePath = `/dashboard/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  if (isLoading) return <PageLoader />;

  if (isError || !issue) {
    return (
      <div className="rounded-2xl border border-destructive/20 bg-destructive/5 p-6 text-sm">
        <p className="font-medium">Could not load issue</p>
        <p className="mt-1 text-muted-foreground">
          {error instanceof Error ? error.message : String(error)}
        </p>
      </div>
    );
  }

  const handleClose = async () => {
    setActionError(null);
    try {
      await closeMutation.mutateAsync();
      router.refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to close issue.");
    }
  };

  const handleComment = async () => {
    setActionError(null);
    if (!comment.trim()) {
      setActionError("Comment cannot be empty.");
      return;
    }
    try {
      await commentMutation.mutateAsync(comment);
      setComment("");
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Failed to add comment.");
    }
  };

  const isOpen = issue.state === "open";

  return (
    <div className="space-y-6">
      <Link
        href={`${basePath}/issues`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> Back to issues
      </Link>

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">#{issue.number}</h2>
          <Badge variant={isOpen ? "success" : "secondary"}>
            {isOpen ? "Open" : "Closed"}
          </Badge>
        </div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{issue.title}</h1>
        <p className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1.5">
            <User className="h-4 w-4" />
            {issue.user && "login" in issue.user ? issue.user.login : "unknown"}
          </span>
          <span>opened {formatRelativeTime(issue.created_at)}</span>
          {issue.comments > 0 && (
            <span className="inline-flex items-center gap-1.5">
              <MessageSquare className="h-4 w-4" />
              {issue.comments} comments
            </span>
          )}
        </p>
        {issue.labels && issue.labels.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {issue.labels
              .filter((l): l is { name: string; color?: string } => !!l && "name" in l)
              .map((l) => (
                <Badge
                  key={l.name}
                  variant="secondary"
                  className="text-[11px]"
                >
                  {l.name}
                </Badge>
              ))}
          </div>
        )}
      </div>

      {isOpen && (
        <div className="flex items-center gap-3">
          <Button onClick={handleClose} variant="outline" disabled={closeMutation.isPending}>
            {closeMutation.isPending ? "Closing…" : "Close issue"}
          </Button>
          {issue.html_url && (
            <Button asChild variant="ghost" size="sm">
              <Link href={issue.html_url} target="_blank" rel="noreferrer">
                View on GitHub
              </Link>
            </Button>
          )}
        </div>
      )}

      {actionError && (
        <p className="text-sm text-destructive" role="alert">
          {actionError}
        </p>
      )}

      {issue.body ? (
        <Card className="glass-card">
          <CardContent className="whitespace-pre-wrap p-5 text-sm leading-relaxed">
            {issue.body}
          </CardContent>
        </Card>
      ) : (
        <Card className="glass-card">
          <CardContent className="p-5 text-sm text-muted-foreground">
            No description provided.
          </CardContent>
        </Card>
      )}

      {isOpen && (
        <Card className="glass-card">
          <CardContent className="space-y-4 p-5">
            <h3 className="flex items-center gap-2 text-base font-semibold">
              <Circle className="h-4 w-4 text-primary" /> Add a comment
            </h3>
            <Textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Share your thoughts…"
              rows={4}
            />
            <Button onClick={handleComment} disabled={commentMutation.isPending} className="gap-2">
              <Send className="h-4 w-4" />
              {commentMutation.isPending ? "Posting…" : "Comment"}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
