"use client";

import { Package, Plus, Tag } from "lucide-react";
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
import { useCreateRelease, useReleases } from "@/hooks/use-repository";
import { formatDateTime } from "@/lib/utils";

function CreateReleaseDialog({ owner, repo }: { owner: string; repo: string }) {
  const createRelease = useCreateRelease(owner, repo);
  const [open, setOpen] = useState(false);
  const [tagName, setTagName] = useState("");
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [prerelease, setPrerelease] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!tagName.trim()) {
      setError("Tag name is required.");
      return;
    }
    try {
      await createRelease.mutateAsync({
        tag_name: tagName.trim(),
        name: name.trim() || undefined,
        body: body || undefined,
        prerelease,
      });
      setOpen(false);
      setTagName("");
      setName("");
      setBody("");
      setPrerelease(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create release.");
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">
          <Plus className="h-4 w-4" /> New release
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New release</DialogTitle>
          <DialogDescription>Tag a commit and publish release notes.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4 py-2">
          <div className="grid gap-2">
            <Label htmlFor="rel-tag">Tag name</Label>
            <Input
              id="rel-tag"
              value={tagName}
              onChange={(e) => setTagName(e.target.value)}
              placeholder="v1.0.0"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="rel-name">Release title</Label>
            <Input
              id="rel-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="v1.0.0"
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="rel-body">Release notes</Label>
            <Textarea
              id="rel-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="What's new in this release?"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={prerelease}
              onChange={(e) => setPrerelease(e.target.checked)}
              className="h-4 w-4 rounded border-border accent-primary"
            />
            This is a pre-release
          </label>
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={createRelease.isPending}>
            {createRelease.isPending ? "Publishing…" : "Publish release"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function ReleasesPage() {
  const params = useParams<{ owner: string; repo: string }>();
  const owner = params.owner;
  const repo = params.repo;

  const releases = useReleases(owner, repo);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Releases</h2>
        <CreateReleaseDialog owner={owner} repo={repo} />
      </div>

      {releases.isLoading ? (
        <PageLoader />
      ) : !releases.data || releases.data.releases.length === 0 ? (
        <EmptyState
          icon={Package}
          title="No releases yet"
          description="Publish your first release to tag a version of this repository."
          action={<CreateReleaseDialog owner={owner} repo={repo} />}
        />
      ) : (
        <div className="space-y-3">
          {releases.data.releases.map((rel) => (
            <Card key={rel.id} className="glass-card">
              <CardContent className="p-5">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Tag className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="font-mono text-sm font-semibold">{rel.tag_name}</h3>
                        {rel.prerelease && <Badge variant="warning">pre-release</Badge>}
                        {rel.draft && <Badge variant="secondary">draft</Badge>}
                      </div>
                      {rel.name && <p className="mt-0.5 text-sm font-medium">{rel.name}</p>}
                      <p className="mt-1 text-xs text-muted-foreground">
                        {rel.published_at
                          ? `Published ${formatDateTime(rel.published_at)}`
                          : "Not published yet"}
                      </p>
                    </div>
                  </div>
                  {rel.html_url && (
                    <Button asChild variant="outline" size="sm">
                      <a href={rel.html_url} target="_blank" rel="noreferrer">
                        View
                      </a>
                    </Button>
                  )}
                </div>
                {rel.body && (
                  <p className="mt-4 whitespace-pre-wrap border-t pt-4 text-sm leading-relaxed text-muted-foreground">
                    {rel.body}
                  </p>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
