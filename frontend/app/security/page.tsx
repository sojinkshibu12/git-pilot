"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Loader2, Lock, MailCheck, ShieldCheck } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";
import type { SecurityOverview } from "@/lib/types";

export default function SecurityPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ current_password: "", new_password: "", confirm: "" });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const { data: overview, isLoading } = useQuery({
    queryKey: ["security"],
    queryFn: () => apiFetch<SecurityOverview>("/users/me/security"),
  });

  const changePassword = useMutation({
    mutationFn: () =>
      apiFetch("/auth/password/change", {
        method: "POST",
        body: JSON.stringify({
          current_password: form.current_password,
          new_password: form.new_password,
        }),
        csrf: true,
      }),
    onSuccess: () => {
      setMessage({ ok: true, text: "Password updated." });
      setForm({ current_password: "", new_password: "", confirm: "" });
      queryClient.invalidateQueries({ queryKey: ["security"] });
    },
    onError: (err) => {
      setMessage({ ok: false, text: err instanceof Error ? err.message : "Failed to update." });
    },
  });

  const disabled =
    !form.current_password ||
    form.new_password.length < 12 ||
    form.new_password !== form.confirm ||
    changePassword.isPending;

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Security</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage password, verification, and session security.
        </p>
      </header>

      {isLoading ? (
        <div className="grid gap-6 md:grid-cols-2">
          <div className="skeleton h-40" />
          <div className="skeleton h-40" />
        </div>
      ) : (
        <>
          <section className="grid gap-4 sm:grid-cols-3">
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
              <Card className="glass-card">
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="rounded-xl bg-primary/10 p-3 text-primary">
                    <Lock className="h-6 w-6" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Password</p>
                    <p className="font-semibold">
                      {overview?.has_password ? "Set" : "Not set"}
                    </p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
              <Card className="glass-card">
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="rounded-xl bg-emerald-500/10 p-3 text-emerald-500">
                    <MailCheck className="h-6 w-6" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Email verified</p>
                    <p className="font-semibold">{overview?.email_verified ? "Yes" : "Pending"}</p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
              <Card className="glass-card">
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="rounded-xl bg-amber-500/10 p-3 text-amber-500">
                    <ShieldCheck className="h-6 w-6" />
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Active sessions</p>
                    <p className="font-semibold">{overview?.active_sessions_count ?? 0}</p>
                  </div>
                </CardContent>
              </Card>
            </motion.div>
          </section>

          <Card className="max-w-lg glass-card">
            <CardHeader>
              <CardTitle>Change password</CardTitle>
              <CardDescription>
                Use a strong, unique password. It&apos;s hashed with Argon2id.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="current">Current password</Label>
                <Input
                  id="current"
                  type="password"
                  autoComplete="current-password"
                  value={form.current_password}
                  onChange={(e) => setForm({ ...form, current_password: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="new">New password</Label>
                <Input
                  id="new"
                  type="password"
                  autoComplete="new-password"
                  value={form.new_password}
                  onChange={(e) => setForm({ ...form, new_password: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="confirm">Confirm new password</Label>
                <Input
                  id="confirm"
                  type="password"
                  autoComplete="new-password"
                  value={form.confirm}
                  onChange={(e) => setForm({ ...form, confirm: e.target.value })}
                />
              </div>
              {message && (
                <p
                  role="status"
                  className={`text-sm ${message.ok ? "text-emerald-600 dark:text-emerald-400" : "text-destructive"}`}
                >
                  {message.text}
                </p>
              )}
              <Button onClick={() => changePassword.mutate()} disabled={disabled}>
                {changePassword.isPending ? <Loader2 className="animate-spin" /> : <Lock />}
                Update password
              </Button>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
