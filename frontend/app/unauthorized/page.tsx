import type { Metadata } from "next";
import Link from "next/link";
import { ShieldX } from "lucide-react";

import { AuroraBackground } from "@/components/layout/aurora-background";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";

export const metadata: Metadata = { title: "Access denied" };

export default function UnauthorizedPage() {
  return (
    <AuroraBackground>
      <div className="flex min-h-screen flex-col">
        <header className="px-6 py-5">
          <Logo />
        </header>
        <main className="flex flex-1 items-center justify-center px-4 pb-16">
          <div className="glass-card w-full max-w-sm p-10 text-center">
            <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              <ShieldX className="h-8 w-8" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Access denied</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              You don&apos;t have permission to view this page. If you believe this is a mistake,
              contact your workspace administrator.
            </p>
            <div className="mt-6 space-y-2">
              <Link href="/dashboard">
                <Button className="w-full">Go to dashboard</Button>
              </Link>
            </div>
          </div>
        </main>
      </div>
    </AuroraBackground>
  );
}
