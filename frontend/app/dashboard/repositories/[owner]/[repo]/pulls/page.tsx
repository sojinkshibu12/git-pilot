"use client";

import { GitPullRequest, GitMerge, Plus, User } from "lucide-react";
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
import {
  useBranches,
  useCreatePullRequest,
  usePullRequests,
} from "@/hooks/use-repository";
import { formatRelativeTime, shortSha } from "@/lib/utils";

function PullRequestBadge({ pr }: { pr: { state: string; merged: boolean } }) {
  if (pr.merged) return <Badge variant="info">Merged</Badge>;
  if (pr.state === "closed") return <Badge variant="destructive">Closed</Badge>;
  return <Badge variant="success">Open</Badge>;
}

function CreatePullRequestDialog({ owner, repo }: { owner: string; repo: string }) {
  const branches = useBranches(owner, repo);
  const createPr = useCreatePullRequest(owner, repo);
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [head, setHead] = useState("");
  const [base, setBase] = useState("main");
  const [error, setError] = useState<string | null>(null);

  const branchesList = branches.data?.branches ?? [];

  const submit = async () => {
    setError(null);
    if (!title.trim() || !head.trim()) {
      setError("Title and head branch are required.");
      return;
    }
    try {
      await createPr.mutateAsync({ title, head, base, body: body || undefined });
      setOpen(false);
      setTitle("");
      setBody("");
      setHead("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create pull request.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4" /> New pull request
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New pull request</DialogTitle>
          <DialogDescription>
            Propose a change from one branch to another.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="pr-head">From (head)</Label>
              <Input
                id="pr-head"
                list="branch-list"
                placeholder="feature/xyz"
                value={head}
                onChange={(e) => setHead(e.target.value)}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="pr-base">Into (base)</Label>
              <Input
                id="pr-base"
                list="branch-list"
                placeholder="main"
                value={base}
                onChange={(e) => setBase(e.target.value)}
              />
            </div>
          </div>
          <datalist id="branch-list">
            {branchesList.map((b) => (
              <option key={b.name} value={b.name} />
            ))}
          </datalist>
          <div className="grid gap-2">
            <Label htmlFor="pr-title">Title</Label>
            <Input
              id="pr-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Describe your change"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="pr-body">Description</Label>
            <Textarea
              id="pr-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="What does this change and why?"
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={createPr.isPending}>
            {createPr.isPending ? "Creating…" : "Create pull request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function PullRequestsPage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = params.owner;
  const repo = params.repo;
  const [state, setState] = useState("open");

  const pulls = usePullRequests(owner, repo, state);
  const basePath = `/dashboard/repositories/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Pull requests</h2>
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
          <CreatePullRequestDialog owner={owner} repo={repo} />
        </div>
      </div>

      {pulls.isLoading ? (
        <PageLoader />
      ) : !pulls.data || pulls.data.pull_requests.length === 0 ? (
        <EmptyState
          icon={GitPullRequest}
          title="No pull requests"
          description={`There are no ${state} pull requests in this repository.`}
          action={<CreatePullRequestDialog owner={owner} repo={repo} />}
        />
      ) : (
        <Card className="glass-card">
          <CardContent className="p-0">
            <ul className="divide-y">
              {pulls.data.pull_requests.map((pr) => (
                <li key={pr.id}>
                  <Link
                    href={`${basePath}/pulls/${pr.number}`}
                    className="group flex items-start gap-4 p-5 transition-colors hover:bg-accent/40"
                  >
                    <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                      <GitMerge className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold group-hover:text-primary">
                          {pr.title}
                        </span>
                        <PullRequestBadge pr={pr} />
                      </div>
                      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                        <span>#{pr.number}</span>
                        <span className="inline-flex items-center gap-1">
                          <User className="h-3 w-3" />
                          {pr.user && "login" in pr.user ? pr.user.login : "unknown"}
                        </span>
                        <span>·</span>
                        <span className="inline-flex items-center gap-1">
                          {pr.base?.ref} ← {pr.head?.ref}
                        </span>
                        {pr.head?.sha && (
                          <>
                            <span>·</span>
                            <code className="font-mono">{shortSha(pr.head.sha)}</code>
                          </>
                        )}
                        {pr.mergeable === false && (
                          <>
                            <span>·</span>
                            <span className="text-destructive">conflicts</span>
                          </>
                        )}
                      </p>
                    </div>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {formatRelativeTime(pr.updated_at ?? pr.created_at)}
                    </span>
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
