"use client";

import { Circle, Plus, GitPullRequest } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";

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
import { useCreateIssue, useIssues } from "@/hooks/use-repository";
import { formatRelativeTime } from "@/lib/utils";

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

function CreateIssueDialog({ owner, repo }: { owner: string; repo: string }) {
  const createIssue = useCreateIssue(owner, repo);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!title.trim()) {
      setError("Title is required.");
      return;
    }
    try {
      await createIssue.mutateAsync({ title, body: body || undefined });
      setOpen(false);
      setTitle("");
      setBody("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create issue.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4" /> New issue
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New issue</DialogTitle>
          <DialogDescription>Report a bug, request a feature, or start a discussion.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="issue-title">Title</Label>
            <Input
              id="issue-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Summarize the issue"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="issue-body">Description</Label>
            <Textarea
              id="issue-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="What's going on?"
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={createIssue.isPending}>
            {createIssue.isPending ? "Creating…" : "Create issue"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function IssuesPage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = params.owner;
  const repo = params.repo;
  const [state, setState] = useState("open");

  const issues = useIssues(owner, repo, state);
  const basePath = `/dashboard/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Issues</h2>
        <div className="flex items-center gap-2">
          {(["open", "closed", "all"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setState(s)}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium capitalize transition-colors ${
                state === s
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent"
              }`}
            >
              {s}
            </button>
          ))}
          <CreateIssueDialog owner={owner} repo={repo} />
        </div>
      </div>

      {issues.isLoading ? (
        <PageLoader />
      ) : !issues.data || issues.data.issues.length === 0 ? (
        <EmptyState
          icon={Circle}
          title="No issues"
          description={`There are no ${state} issues in this repository.`}
          action={<CreateIssueDialog owner={owner} repo={repo} />}
        />
      ) : (
        <Card className="glass-card">
          <CardContent className="p-0">
            <ul className="divide-y">
              {issues.data.issues.map((issue) => (
                <li key={issue.id}>
                  <Link
                    href={`${basePath}/issues/${issue.number}`}
                    className="group flex items-start gap-4 p-5 transition-colors hover:bg-accent/40"
                  >
                    {issue.pull_request ? (
                      <GitPullRequest className="mt-1 h-4 w-4 shrink-0 text-emerald-500" />
                    ) : (
                      <Circle
                        className={`mt-1 h-4 w-4 shrink-0 ${
                          issue.state === "open"
                            ? "fill-emerald-500/20 text-emerald-500"
                            : "fill-muted text-muted-foreground"
                        }`}
                      />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold group-hover:text-primary">
                          {issue.title}
                        </span>
                        {issue.state === "closed" && <Badge variant="secondary">closed</Badge>}
                      </div>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <span>#{issue.number}</span>
                        {issue.user && "login" in issue.user && (
                          <>
                            <span>·</span>
                            <span>{issue.user.login}</span>
                          </>
                        )}
                        <span>·</span>
                        <span>opened {formatRelativeTime(issue.created_at)}</span>
                        {issue.comments > 0 && (
                          <>
                            <span>·</span>
                            <span>{issue.comments} comments</span>
                          </>
                        )}
                      </div>
                      {issue.labels && issue.labels.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {issue.labels
                            .filter((l): l is { name: string; color?: string } => !!l && "name" in l)
                            .slice(0, 5)
                            .map((l) => (
                              <IssueLabel key={l.name} name={l.name} color={l.color} />
                            ))}
                        </div>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
