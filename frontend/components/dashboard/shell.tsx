"use client";

import { motion } from "framer-motion";
import {
  LayoutDashboard,
  Link2,
  LogOut,
  MonitorSmartphone,
  ShieldCheck,
  Github,
  GitFork,
  Inbox,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useState } from "react";

import { Logo } from "@/components/layout/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/dashboard/repositories", label: "Repositories", icon: GitFork },
  { href: "/dashboard/issues", label: "Assigned issues", icon: Inbox },
  { href: "/security", label: "Security", icon: ShieldCheck },
  { href: "/security/connected-accounts", label: "Connected accounts", icon: Link2 },
  { href: "/security/sessions", label: "Active sessions", icon: MonitorSmartphone },
];

export function DashboardShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);

  const logout = async () => {
    setSigningOut(true);
    try {
      await apiFetch("/auth/logout", { method: "POST" });
    } finally {
      window.location.assign("/login");
    }
  };

  return (
    <div className="flex min-h-screen bg-background">
      {/* Sidebar */}
      <aside className="sticky top-0 hidden h-screen w-64 flex-col border-r bg-card/40 backdrop-blur-xl md:flex">
        <div className="flex h-16 items-center border-b px-5">
          <Logo />
        </div>
        <nav className="flex-1 space-y-1 p-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== "/dashboard" && pathname.startsWith(href));
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  active
                    ? "text-primary"
                    : "text-muted-foreground hover:bg-accent hover:text-foreground",
                )}
              >
                {active && (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-lg bg-primary/10"
                    transition={{ type: "spring", stiffness: 400, damping: 32 }}
                  />
                )}
                <Icon className="relative z-10 h-4 w-4" />
                <span className="relative z-10">{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className="space-y-2 border-t p-3">
          <ThemeToggle />
          <Button
            variant="outline"
            size="sm"
            className="w-full justify-start gap-2 text-muted-foreground"
            onClick={logout}
            disabled={signingOut}
          >
            <LogOut className="h-4 w-4" />
            {signingOut ? "Signing out…" : "Sign out"}
          </Button>
        </div>
      </aside>

      {/* Mobile header */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b bg-background/80 px-4 backdrop-blur-xl md:hidden">
          <Logo />
          <ThemeToggle />
        </header>
        <main className="flex-1 p-4 sm:p-8">{children}</main>
      </div>
    </div>
  );
}

export function GithubBadge({ login }: { login?: string | null }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 px-2.5 py-1 text-xs font-medium">
      <Github className="h-3 w-3" />
      {login ?? "GitHub"}
    </span>
  );
}
