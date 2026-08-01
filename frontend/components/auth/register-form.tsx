"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { motion } from "framer-motion";
import { Check, Loader2, ShieldCheck, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { GitHubButton } from "@/components/auth/github-button";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";

const registerSchema = z
  .object({
    display_name: z.string().min(1, "Display name is required.").max(160),
    email: z.string().email("Enter a valid email address."),
    password: z
      .string()
      .min(12, "At least 12 characters.")
      .regex(/[A-Z]/, "Must include an uppercase letter.")
      .regex(/[a-z]/, "Must include a lowercase letter.")
      .regex(/[0-9]/, "Must include a number."),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "Passwords do not match.",
    path: ["confirm"],
  });

type RegisterValues = z.infer<typeof registerSchema>;

const PASSWORD_CHECKS = [
  { label: "12+ characters", test: (p: string) => p.length >= 12 },
  { label: "Uppercase", test: (p: string) => /[A-Z]/.test(p) },
  { label: "Lowercase", test: (p: string) => /[a-z]/.test(p) },
  { label: "Number", test: (p: string) => /[0-9]/.test(p) },
];

export function RegisterForm() {
  const router = useRouter();
  const [serverError, setServerError] = useState<string | null>(null);
  const [created, setCreated] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: { display_name: "", email: "", password: "", confirm: "" },
  });

  const password = watch("password") ?? "";

  const onSubmit = async (values: RegisterValues) => {
    setServerError(null);
    try {
      await apiFetch("/auth/register", {
        method: "POST",
        body: JSON.stringify({
          email: values.email,
          password: values.password,
          display_name: values.display_name,
        }),
      });
      setCreated(true);
    } catch (err) {
      setServerError(err instanceof Error ? err.message : "Registration failed.");
    }
  };

  if (created) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="space-y-4 text-center"
      >
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500">
          <Check className="h-7 w-7" />
        </div>
        <h3 className="text-xl font-semibold">Check your inbox</h3>
        <p className="text-sm text-muted-foreground">
          We sent a verification link to <strong>{watch("email")}</strong>. In development, the
          token is returned by the API.
        </p>
        <Button variant="outline" className="w-full" onClick={() => router.push("/login")}>
          Back to sign in
        </Button>
      </motion.div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-5" noValidate>
      <div className="space-y-2">
        <Label htmlFor="display_name">Display name</Label>
        <Input
          id="display_name"
          placeholder="Ada Lovelace"
          autoComplete="name"
          {...register("display_name")}
        />
        {errors.display_name && <p className="text-xs text-destructive">{errors.display_name.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="email">Work email</Label>
        <Input
          id="email"
          type="email"
          placeholder="you@company.com"
          autoComplete="email"
          {...register("email")}
        />
        {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          placeholder="Create a strong password"
          {...register("password")}
        />
        <div className="flex flex-wrap gap-2 pt-1">
          {PASSWORD_CHECKS.map((c) => {
            const ok = c.test(password);
            return (
              <span
                key={c.label}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${
                  ok
                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {ok && <Check className="h-3 w-3" />}
                {c.label}
              </span>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="confirm">Confirm password</Label>
        <Input
          id="confirm"
          type="password"
          autoComplete="new-password"
          placeholder="Repeat your password"
          {...register("confirm")}
        />
        {errors.confirm && <p className="text-xs text-destructive">{errors.confirm.message}</p>}
      </div>

      <div className="flex items-start gap-2 rounded-lg bg-muted/50 px-3 py-2 text-xs text-muted-foreground">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
        <p>
          Your GitHub tokens are encrypted with AES-256-GCM and never touch your browser. We only
          request the minimum scopes needed.
        </p>
      </div>

      {serverError && (
        <div role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {serverError}
        </div>
      )}

      <Button type="submit" size="lg" className="w-full" disabled={isSubmitting}>
        {isSubmitting ? <Loader2 className="animate-spin" /> : <UserPlus />}
        {isSubmitting ? "Creating account…" : "Create account"}
      </Button>

      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">or</span>
        </div>
      </div>

      <GitHubButton label="Sign up with GitHub" />
    </form>
  );
}
