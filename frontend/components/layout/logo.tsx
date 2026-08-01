import Link from "next/link";

import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <Link href="/" className={cn("group inline-flex items-center gap-2.5", className)}>
      <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 via-indigo-500 to-sky-500 shadow-lg shadow-indigo-500/25 transition-transform group-hover:scale-105">
        <svg viewBox="0 0 24 24" className="h-5 w-5 text-white" fill="none" aria-hidden>
          <path
            d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinejoin="round"
          />
          <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="text-lg font-semibold tracking-tight">
        Git<span className="text-gradient">Pilot</span>
      </span>
    </Link>
  );
}
