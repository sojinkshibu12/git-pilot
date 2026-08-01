import type { Metadata } from "next";
import Link from "next/link";
import { Timer } from "lucide-react";

import { AuroraBackground } from "@/components/layout/aurora-background";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Session expired" };

export default function SessionExpiredPage() {
  return (
    <AuroraBackground>
      <div className="flex min-h-screen flex-col">
        <header className="px-6 py-5">
          <Logo />
        </header>
        <main className="flex flex-1 items-center justify-center px-4 pb-16">
          <div className="glass-card w-full max-w-sm p-10 text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-amber-500/10 text-amber-500">
              <Timer className="h-8 w-8" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Session expired</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              For your security, your session expired after a period of inactivity. Your data is
              safe — sign in again to continue.
            </p>
            <div className="mt-6 space-y-2">
              <Link href="/login">
                <Button className="w-full">Sign in again</Button>
              </Link>
            </div>
          </div>
        </main>
      </div>
    </AuroraBackground>
  );
}
