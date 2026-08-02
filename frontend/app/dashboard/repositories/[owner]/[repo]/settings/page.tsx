"use client";

import { AlertTriangle, Plus, ShieldAlert, Trash2, Users } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import {
  useCollaborators,
  useCreateLabel,
  useDeleteRepository,
  useLabels,
} from "@/hooks/use-repository";
import { ApiError } from "@/lib/api";

function CreateLabelDialog({ owner, repo }: { owner: string; repo: string }) {
  const createLabel = useCreateLabel(owner, repo);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [color, setColor] = useState("1F883D");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!name.trim()) {
      setError("Label name is required.");
      return;
    }
    if (!/^[0-9a-fA-F]{6}$/.test(color)) {
      setError("Color must be a 6-digit hex value (e.g. 1F883D).");
      return;
    }
    try {
      await createLabel.mutateAsync({
        name: name.trim(),
        color: color.toUpperCase(),
        description: description.trim() || undefined,
      });
      setOpen(false);
      setName("");
      setColor("1F883D");
      setDescription("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create label.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4" /> New label
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New label</DialogTitle>
          <DialogDescription>Add a reusable label for issues and pull requests.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="label-name">Name</Label>
            <Input
              id="label-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="bug"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="label-color">Color (hex)</Label>
            <div className="flex items-center gap-3">
              <input
                id="label-color"
                type="color"
                value={`#${color}`}
                onChange={(e) => setColor(e.target.value.replace("#", ""))}
                className="h-10 w-14 cursor-pointer rounded-lg border border-input bg-background p-1"
              />
              <Input
                value={color}
                onChange={(e) => setColor(e.target.value)}
                className="font-mono uppercase"
                maxLength={6}
              />
            </div>
          </div>
          <div className="grid gap-2">
            <Label htmlFor="label-desc">Description</Label>
            <Input
              id="label-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Something went wrong"
            />
          </div>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={createLabel.isPending}>
            {createLabel.isPending ? "Creating…" : "Create label"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DeleteRepoDialog({ owner, repo }: { owner: string; repo: string }) {
  const router = useRouter();
  const deleteRepo = useDeleteRepository(owner, repo);
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);

  const fullName = `${owner}/${repo}`;

  const submit = async () => {
    setError(null);
    if (confirm.trim() !== fullName) {
      setError(`Type ${fullName} to confirm.`);
      return;
    }
    try {
      await deleteRepo.mutateAsync();
      router.replace("/dashboard/repositories");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to delete repository.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm">
          <Trash2 className="h-4 w-4" /> Delete repository
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-destructive">Delete repository</DialogTitle>
          <DialogDescription>
            This permanently deletes the GitHub repository. This action cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <p className="text-sm text-muted-foreground">
            Type <code className="rounded bg-muted px-1.5 py-0.5 font-mono">{fullName}</code> to
            confirm.
          </p>
          <Input
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder={fullName}
            className="font-mono"
          />
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={submit}
            disabled={deleteRepo.isPending || confirm.trim() !== fullName}
          >
            {deleteRepo.isPending ? "Deleting…" : "Delete repository"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function RepositorySettingsPage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = params.owner;
  const repo = params.repo;

  const labels = useLabels(owner, repo);
  const collaborators = useCollaborators(owner, repo);

  return (
    <div className="space-y-6">
      <section>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-lg font-semibold">Labels</h2>
          <CreateLabelDialog owner={owner} repo={repo} />
        </div>
        {labels.isLoading ? (
          <PageLoader />
        ) : !labels.data || labels.data.labels.length === 0 ? (
          <EmptyState
            icon={Plus}
            title="No labels yet"
            description="Create labels to organize issues and pull requests."
            action={<CreateLabelDialog owner={owner} repo={repo} />}
          />
        ) : (
          <div className="flex flex-wrap gap-2">
            {labels.data.labels.map((l) => {
              const bg = /^[0-9a-fA-F]{6}$/.test(l.color) ? `#${l.color}` : undefined;
              return (
                <span
                  key={l.id}
                  title={l.description ?? undefined}
                  className="inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium"
                  style={
                    bg
                      ? {
                          backgroundColor: `${bg}22`,
                          borderColor: `${bg}55`,
                          color: bg,
                        }
                      : undefined
                  }
                >
                  <span
                    className="h-2 w-2 rounded-full"
                    style={{ backgroundColor: bg ?? "currentColor" }}
                  />
                  {l.name}
                </span>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold">
          <Users className="h-5 w-5 text-muted-foreground" /> Collaborators
        </h2>
        {collaborators.isLoading ? (
          <PageLoader />
        ) : !collaborators.data || collaborators.data.collaborators.length === 0 ? (
          <EmptyState icon={Users} title="No collaborators found" />
        ) : (
          <Card className="glass-card">
            <CardContent className="p-0">
              <ul className="divide-y">
                {collaborators.data.collaborators.map((c) => (
                  <li key={c.id} className="flex items-center gap-3 p-4">
                    {c.avatar_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={c.avatar_url}
                        alt=""
                        className="h-8 w-8 rounded-full ring-1 ring-border"
                      />
                    ) : (
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-xs font-bold text-primary">
                        {c.login.slice(0, 2).toUpperCase()}
                      </div>
                    )}
                    <span className="text-sm font-medium">{c.login}</span>
                    {c.site_admin && <Badge variant="secondary">site admin</Badge>}
                    <span className="ml-auto text-xs text-muted-foreground">
                      {c.type ?? "User"}
                    </span>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </section>

      <section>
        <h2 className="mb-3 flex items-center gap-2 text-lg font-semibold text-destructive">
          <ShieldAlert className="h-5 w-5" /> Danger zone
        </h2>
        <Card className="border-destructive/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle className="h-4 w-4 text-destructive" /> Delete this repository
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Deleting a repository removes it and all of its data from GitHub. There is no
              undo. The action is irreversible.
            </p>
            <DeleteRepoDialog owner={owner} repo={repo} />
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
