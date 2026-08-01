import Link from "next/link";
import { Compass } from "lucide-react";

import { AuroraBackground } from "@/components/layout/aurora-background";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <AuroraBackground>
      <div className="flex min-h-screen flex-col">
        <header className="px-6 py-5">
          <Logo />
        </header>
        <main className="flex flex-1 items-center justify-center px-4 pb-16">
          <div className="glass-card w-full max-w-sm p-10 text-center">
            <p className="text-gradient text-7xl font-black tracking-tight">404</p>
            <h1 className="mt-3 text-xl font-semibold">Page not found</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              The page you&apos;re looking for doesn&apos;t exist or was moved.
            </p>
            <div className="mt-6 flex justify-center gap-2">
              <Link href="/dashboard">
                <Button>
                  <Compass /> Go home
                </Button>
              </Link>
            </div>
          </div>
        </main>
      </div>
    </AuroraBackground>
  );
}
