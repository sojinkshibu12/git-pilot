"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { Link2, Loader2 } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";

const schema = z.object({
  email: z.string().email("Enter a valid email."),
  password: z.string().min(1, "Enter the password for your existing account."),
});

type Values = z.infer<typeof schema>;

/**
 * Account linking screen: a GitHub sign-in detected an existing account with the
 * same email. Prove ownership by entering that account's password. The GitHub
 * identity is only attached after the password verifies.
 */
export function LinkForm() {
  const router = useRouter();
  const search = useSearchParams();
  const linkToken = search.get("link_token") ?? "";
  const githubLogin = search.get("github_login") ?? "your GitHub account";
  const [error, setError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = async (values: Values) => {
    setError(null);
    try {
      await apiFetch("/oauth/link/complete", {
        method: "POST",
        body: JSON.stringify({
          link_token: linkToken,
          password: values.password,
          email: values.email,
        }),
      });
      router.push("/dashboard");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Linking failed.");
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
      <div className="flex items-center gap-3 rounded-xl border border-primary/20 bg-primary/5 px-4 py-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/15 text-primary">
          <Link2 className="h-5 w-5" />
        </div>
        <p className="text-sm text-foreground">
          Link <strong>@{githubLogin}</strong> to an existing GitPilot account.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="email">Existing account email</Label>
        <Input id="email" type="email" placeholder="you@company.com" {...register("email")} />
        {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Existing account password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          placeholder="Password of your existing account"
          {...register("password")}
        />
        {errors.password && <p className="text-xs text-destructive">{errors.password.message}</p>}
      </div>

      <p className="text-xs text-muted-foreground">
        This confirms you own the existing account. No duplicate accounts are created.
      </p>

      {error && (
        <motion.div
          initial={{ opacity: 0, y: -6 }}
          animate={{ opacity: 1, y: 0 }}
          role="alert"
          className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {error}
        </motion.div>
      )}

      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting || !linkToken}>
        {isSubmitting ? <Loader2 className="animate-spin" /> : <Link2 />}
        {isSubmitting ? "Linking…" : "Link accounts"}
      </Button>

      {!linkToken && (
        <p className="text-center text-xs text-destructive">This link is invalid or expired.</p>
      )}
    </form>
  );
}

export function AccountLinkScreen() {
  return (
    <Suspense>
      <LinkForm />
    </Suspense>
  );
}
