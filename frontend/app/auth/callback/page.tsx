"use client";

import { motion } from "framer-motion";
import { AlertTriangle, CheckCircle2, Link2, Loader2, XCircle } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AccountLinkScreen } from "@/components/auth/link-form";
import { AuroraBackground } from "@/components/layout/aurora-background";
import { Logo } from "@/components/layout/logo";
import { Button } from "@/components/ui/button";

/**
 * OAuth callback screen. The backend performs all token exchange and redirects
 * here with a status. Renders loading, success, or the account-linking flow.
 */
function CallbackContent() {
  const router = useRouter();
  const search = useSearchParams();
  const status = search.get("status") ?? "";
  const linkToken = search.get("link_token");

  const [waiting, setWaiting] = useState(true);
  useEffect(() => {
    if (status === "success") {
      const t = setTimeout(() => {
        router.replace("/dashboard");
      }, 1200);
      return () => clearTimeout(t);
    }
    setWaiting(false);
    return undefined;
  }, [status, router]);

  // Linking required — GitHub identity needs to be attached to an existing account.
  if (status === "link_required" && linkToken) {
    return (
      <main className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="glass-card w-full max-w-md p-8 sm:p-10">
          <div className="mb-6 space-y-2 text-center">
            <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-primary/15 text-primary">
              <Link2 className="h-7 w-7" />
            </div>
            <h1 className="text-2xl font-semibold tracking-tight">Account already exists</h1>
            <p className="text-sm text-muted-foreground">
              We found an existing account with this email. Link your GitHub identity to continue.
            </p>
          </div>
          <AccountLinkScreen />
        </div>
      </main>
    );
  }

  const errorStates: Record<string, { title: string; message: string }> = {
    cancelled: {
      title: "Authorization cancelled",
      message: "You closed the GitHub authorization window. No changes were made.",
    },
    state_expired: {
      title: "Link expired",
      message: "This sign-in link expired. Please start again.",
    },
    state_mismatch: {
      title: "Security check failed",
      message: "The sign-in request could not be verified. Please try again.",
    },
    error: {
      title: "Something went wrong",
      message: "We couldn't complete the sign-in. Please try again.",
    },
  };

  const isError = status && status !== "success";

  return (
    <main className="flex flex-1 flex-col items-center justify-center px-4 pb-16 text-center">
      <div className="glass-card w-full max-w-sm p-10">
        {status === "success" ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="space-y-4"
          >
            <motion.div
              animate={{ rotate: [0, 360] }}
              transition={{ duration: 1.2, repeat: Infinity, ease: "linear" }}
              className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-primary"
            >
              <Loader2 className="h-8 w-8" />
            </motion.div>
            <div>
              <h1 className="text-xl font-semibold">Authenticating…</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                Securely connecting to GitHub.
              </p>
            </div>
          </motion.div>
        ) : isError ? (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-4"
          >
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10 text-destructive">
              {status === "cancelled" ? (
                <XCircle className="h-8 w-8" />
              ) : (
                <AlertTriangle className="h-8 w-8" />
              )}
            </div>
            <div>
              <h1 className="text-xl font-semibold">{errorStates[status]?.title ?? "Sign-in failed"}</h1>
              <p className="mt-1 text-sm text-muted-foreground">
                {errorStates[status]?.message ?? "Please try again."}
              </p>
            </div>
            <Button className="w-full" onClick={() => router.push("/login")}>
              Back to sign in
            </Button>
          </motion.div>
        ) : (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-4">
            <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-500">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <p className="text-sm text-muted-foreground">Redirecting…</p>
          </motion.div>
        )}
      </div>
    </main>
  );
}

export default function CallbackPage() {
  return (
    <AuroraBackground>
      <div className="flex min-h-screen flex-col">
        <header className="flex items-center justify-between px-6 py-5">
          <Logo />
        </header>
        <Suspense>
          <CallbackContent />
        </Suspense>
      </div>
    </AuroraBackground>
  );
}
