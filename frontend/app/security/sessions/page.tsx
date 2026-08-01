"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Laptop, MonitorSmartphone, Smartphone, XCircle } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";
import { formatRelativeTime } from "@/lib/utils";

interface SessionsResponse {
  sessions: SessionInfo[];
}

function DeviceIcon({ ua }: { ua: string | null }) {
  const s = (ua ?? "").toLowerCase();
  if (s.includes("mobile") || s.includes("android") || s.includes("iphone")) {
    return <Smartphone className="h-5 w-5" />;
  }
  if (s.includes("tablet") || s.includes("ipad")) {
    return <MonitorSmartphone className="h-5 w-5" />;
  }
  return <Laptop className="h-5 w-5" />;
}

export default function SessionsPage() {
  const queryClient = useQueryClient();
  const [action, setAction] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => apiFetch<SessionsResponse>("/sessions/"),
  });

  const revoke = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/sessions/${id}/revoke`, { method: "POST", csrf: true }),
    onMutate: (id) => setAction(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
    onSettled: () => setAction(null),
  });

  const revokeAll = useMutation({
    mutationFn: () => apiFetch("/sessions/revoke-all", { method: "POST", csrf: true }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["sessions"] }),
  });

  const sessions = data?.sessions ?? [];

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Active sessions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Devices currently signed in to your account.
          </p>
        </div>
        <Button variant="outline" onClick={() => revokeAll.mutate()} disabled={revokeAll.isPending}>
          Sign out all other devices
        </Button>
      </header>

      <div className="max-w-2xl space-y-3">
        {isLoading &&
          [0, 1, 2].map((i) => <div key={i} className="skeleton h-20" />)}

        {sessions.map((s, i) => (
          <motion.div
            key={s.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.04 }}
          >
            <Card className="glass-card">
              <CardContent className="flex items-center justify-between gap-4 p-5">
                <div className="flex min-w-0 items-center gap-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <DeviceIcon ua={s.user_agent} />
                  </div>
                  <div className="min-w-0">
                    <p className="flex items-center gap-2 font-medium">
                      {s.device_label ?? "Web browser"}
                      {s.is_current && (
                        <span className="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] font-medium text-primary">
                          This device
                        </span>
                      )}
                    </p>
                    <p className="truncate text-sm text-muted-foreground">
                      {s.user_agent ?? "Unknown device"} ·{" "}
                      {s.ip_address ?? "Unknown IP"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Last active {formatRelativeTime(s.last_used_at)} · Signed in{" "}
                      {formatRelativeTime(s.created_at)}
                    </p>
                  </div>
                </div>
                {!s.is_current && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                    disabled={revoke.isPending && action === s.id}
                    onClick={() => revoke.mutate(s.id)}
                  >
                    <XCircle className="h-4 w-4" /> Revoke
                  </Button>
                )}
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
