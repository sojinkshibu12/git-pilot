import Link from "next/link";

import { AuroraBackground } from "@/components/layout/aurora-background";
import { Logo } from "@/components/layout/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { GitHubButton } from "@/components/auth/github-button";
import { Button } from "@/components/ui/button";

export default function HomePage() {
  return (
    <AuroraBackground>
      <header className="flex items-center justify-between px-6 py-5 lg:px-12">
        <Logo />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link href="/login">
            <Button variant="ghost">Sign in</Button>
          </Link>
        </div>
      </header>

      <main className="flex flex-1 flex-col items-center justify-center px-6 text-center">
        <div className="max-w-2xl space-y-8">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/20 bg-primary/5 px-4 py-1.5 text-xs font-medium text-primary">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            SOC 2-ready · OAuth 2.1 · PKCE
          </div>

          <h1 className="text-4xl font-bold tracking-tight sm:text-6xl">
            Your AI GitHub copilot,{" "}
            <span className="text-gradient">secured end to end.</span>
          </h1>

          <p className="mx-auto max-w-xl text-lg text-muted-foreground">
            GitPilot connects to your GitHub with enterprise-grade auth — encrypted tokens,
            granular permissions, and a complete audit trail. Read, review, and ship from one place.
          </p>

          <div className="flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/register">
              <Button size="lg" className="w-full sm:w-auto">
                Get started free
              </Button>
            </Link>
            <div className="w-full sm:w-72">
              <GitHubButton label="Continue with GitHub" />
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            OAuth 2.1 · PKCE (S256) · Server-side tokens · AES-256-GCM encryption
          </p>
        </div>
      </main>
    </AuroraBackground>
  );
}
