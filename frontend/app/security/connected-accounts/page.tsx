"use client";

import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Check, Github, Mail, Link2 } from "lucide-react";

import { GitHubButton } from "@/components/auth/github-button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";
import type { ConnectedAccount } from "@/lib/types";

interface AccountsResponse {
  accounts: ConnectedAccount[];
}

const PROVIDER_META: Record<string, { label: string; icon: typeof Github; soon?: boolean }> = {
  github: { label: "GitHub", icon: Github },
  email: { label: "Email & Password", icon: Mail },
  google: { label: "Google", icon: Github, soon: true },
  microsoft: { label: "Microsoft", icon: Github, soon: true },
  gitlab: { label: "GitLab", icon: Github, soon: true },
};

export default function ConnectedAccountsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["connected-accounts"],
    queryFn: () => apiFetch<AccountsResponse>("/users/me/connected-accounts"),
  });

  const accounts = data?.accounts ?? [];

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Connected accounts</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage the identity providers linked to your account.
        </p>
      </header>

      <div className="max-w-xl space-y-3">
        {isLoading && (
          <div className="space-y-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="skeleton h-20" />
            ))}
          </div>
        )}

        {accounts.map((account, i) => {
          const meta = PROVIDER_META[account.provider] ?? { label: account.provider, icon: Github };
          const Icon = meta.icon;
          return (
            <motion.div
              key={account.provider}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Card className="glass-card">
                <CardContent className="flex items-center justify-between p-5">
                  <div className="flex items-center gap-4">
                    <div
                      className={`flex h-11 w-11 items-center justify-center rounded-xl ${
                        account.connected
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="font-medium">
                        {meta.label}
                        {meta.soon && (
                          <span className="ml-2 rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase text-muted-foreground">
                            soon
                          </span>
                        )}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {account.connected
                          ? account.login ?? account.email ?? "Connected"
                          : meta.soon
                            ? "Coming soon"
                            : "Not connected"}
                      </p>
                    </div>
                  </div>

                  {account.connected ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                      <Check className="h-3.5 w-3.5" /> Connected
                    </span>
                  ) : meta.soon ? (
                    <span className="text-xs text-muted-foreground">—</span>
                  ) : (
                    <div className="w-48">
                      <GitHubButton label="Connect GitHub" />
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          );
        })}

        <div className="flex items-start gap-3 rounded-xl border border-primary/20 bg-primary/5 p-4 text-sm text-muted-foreground">
          <Link2 className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
          <p>
            Connecting your GitHub account lets GitPilot read repositories, open pull requests,
            and run workflows on your behalf — always with your permission and an audit trail.
          </p>
        </div>
      </div>
    </div>
  );
}
