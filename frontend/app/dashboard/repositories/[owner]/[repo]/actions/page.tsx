"use client";

import { Activity, Play, RefreshCw } from "lucide-react";
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
import { Select } from "@/components/ui/select";
import { PageLoader } from "@/components/ui/spinner";
import { useDispatchWorkflow, useWorkflowRuns, useWorkflows } from "@/hooks/use-repository";
import { formatRelativeTime, shortSha } from "@/lib/utils";
import { cn } from "@/lib/utils";

function RunStatus({ status, conclusion }: { status?: string | null; conclusion?: string | null }) {
  if (conclusion === "success") return <Badge variant="success">success</Badge>;
  if (conclusion === "failure" || conclusion === "cancelled" || conclusion === "timed_out")
    return <Badge variant="destructive">{conclusion}</Badge>;
  if (status === "completed") return <Badge variant="secondary">{conclusion ?? "completed"}</Badge>;
  if (status === "queued") return <Badge variant="info">queued</Badge>;
  if (status === "in_progress") return <Badge variant="warning">in progress</Badge>;
  return <Badge variant="secondary">{status ?? "unknown"}</Badge>;
}

function DispatchWorkflowDialog({ owner, repo }: { owner: string; repo: string }) {
  const workflows = useWorkflows(owner, repo);
  const dispatch = useDispatchWorkflow(owner, repo);
  const [open, setOpen] = useState(false);
  const [workflowId, setWorkflowId] = useState("");
  const [ref, setRef] = useState("main");
  const [inputs, setInputs] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!workflowId || !ref.trim()) {
      setError("Workflow and ref are required.");
      return;
    }
    let parsed: Record<string, string> | undefined;
    if (inputs.trim()) {
      try {
        parsed = JSON.parse(inputs) as Record<string, string>;
      } catch {
        setError("Inputs must be valid JSON.");
        return;
      }
    }
    try {
      await dispatch.mutateAsync({ workflow_id: workflowId, ref: ref.trim(), inputs: parsed });
      setOpen(false);
      setInputs("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to dispatch workflow.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Play className="h-4 w-4" /> Run workflow
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Run workflow</DialogTitle>
          <DialogDescription>Trigger a GitHub Actions workflow_dispatch event.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="wf-select">Workflow</Label>
            <Select
              id="wf-select"
              value={workflowId}
              onChange={(e) => setWorkflowId(e.target.value)}
            >
              <option value="">Select a workflow…</option>
              {(workflows.data?.workflows ?? []).map((wf) => (
                <option key={wf.id} value={String(wf.id)}>
                  {wf.name} ({wf.path})
                </option>
              ))}
            </Select>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wf-ref">Ref (branch / tag)</Label>
            <Input
              id="wf-ref"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
              placeholder="main"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="wf-inputs">Inputs (JSON, optional)</Label>
            <Input
              id="wf-inputs"
              value={inputs}
              onChange={(e) => setInputs(e.target.value)}
              placeholder='{"environment": "staging"}'
              className="font-mono"
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={dispatch.isPending}>
            {dispatch.isPending ? "Dispatching…" : "Run workflow"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function ActionsPage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = params.owner;
  const repo = params.repo;

  const runs = useWorkflowRuns(owner, repo);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Workflow runs</h2>
        <DispatchWorkflowDialog owner={owner} repo={repo} />
      </div>

      {runs.isLoading ? (
        <PageLoader />
      ) : !runs.data || runs.data.workflow_runs.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No workflow runs"
          description="GitHub Actions runs for this repository will appear here."
          action={<DispatchWorkflowDialog owner={owner} repo={repo} />}
        />
      ) : (
        <Card className="glass-card">
          <CardContent className="p-0">
            <ul className="divide-y">
              {runs.data.workflow_runs.map((run) => (
                <li key={run.id} className="flex items-start gap-4 p-5">
                  <div
                    className={cn(
                      "mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg",
                      run.conclusion === "success"
                        ? "bg-emerald-500/10 text-emerald-500"
                        : run.conclusion === "failure"
                          ? "bg-destructive/10 text-destructive"
                          : "bg-primary/10 text-primary",
                    )}
                  >
                    <Activity className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold">
                        {run.name ?? `Run #${run.run_number}`}
                      </span>
                      <RunStatus status={run.status} conclusion={run.conclusion} />
                    </div>
                    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted-foreground">
                      <span>#{run.run_number}</span>
                      {run.event && (
                        <span className="rounded bg-muted px-1.5 py-0.5 font-mono">
                          {run.event}
                        </span>
                      )}
                      {run.head_branch && (
                        <span className="inline-flex items-center gap-1">
                          <RefreshCw className="h-3 w-3" />
                          {run.head_branch}
                        </span>
                      )}
                      {run.head_sha && <code className="font-mono">{shortSha(run.head_sha)}</code>}
                      <span>· {formatRelativeTime(run.created_at)}</span>
                    </p>
                  </div>
                  {run.html_url && (
                    <Button asChild variant="ghost" size="sm">
                      <a href={run.html_url} target="_blank" rel="noreferrer">
                        Details
                      </a>
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
