import type { Metadata } from "next";
import Link from "next/link";

import { LoginForm } from "@/components/auth/login-form";
import { AuroraBackground } from "@/components/layout/aurora-background";
import { Logo } from "@/components/layout/logo";
import { ThemeToggle } from "@/components/layout/theme-toggle";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <AuroraBackground>
      <div className="flex min-h-screen flex-col">
        <header className="flex items-center justify-between px-6 py-5">
          <Logo />
          <ThemeToggle />
        </header>

        <main className="flex flex-1 items-center justify-center px-4 pb-16">
          <div className="glass-card w-full max-w-md p-8 sm:p-10">
            <div className="mb-8 space-y-2">
              <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
              <p className="text-sm text-muted-foreground">
                Sign in to your GitPilot workspace.
              </p>
            </div>
            <LoginForm />
            <p className="mt-8 text-center text-sm text-muted-foreground">
              New to GitPilot?{" "}
              <Link href="/register" className="font-medium text-primary hover:underline">
                Create an account
              </Link>
            </p>
          </div>
        </main>
      </div>
    </AuroraBackground>
  );
}
