"use client";

import { useEffect } from "react";
import { RefreshCw, TriangleAlert } from "lucide-react";

import { AuroraBackground } from "@/components/layout/aurora-background";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";

export default function ErrorPage({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <AuroraBackground>
      <div className="flex min-h-screen flex-col">
        <header className="px-6 py-5">
          <Logo />
        </header>
        <main className="flex flex-1 items-center justify-center px-4 pb-16">
          <div className="glass-card w-full max-w-sm p-10 text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <TriangleAlert className="h-8 w-8" />
            </div>
            <p className="text-gradient text-6xl font-black tracking-tight">500</p>
            <h1 className="mt-3 text-xl font-semibold">Something went wrong</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              An unexpected error occurred. We&apos;ve been notified and are looking into it.
              {error.digest ? ` (ref: ${error.digest})` : ""}
            </p>
            <div className="mt-6 space-y-2">
              <Button className="w-full" onClick={reset}>
                <RefreshCw /> Try again
              </Button>
            </div>
          </div>
        </main>
      </div>
    </AuroraBackground>
  );
}
