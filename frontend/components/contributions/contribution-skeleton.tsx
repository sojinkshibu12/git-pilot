"use client";

import { motion } from "framer-motion";

export function ContributionSkeleton() {
  const rows = [0, 1, 2, 3, 4, 5, 6];
  const weeks = Array.from({ length: 53 });
  return (
    <div className="space-y-3" aria-hidden="true">
      <div className="flex items-center justify-between">
        <div className="h-5 w-40 animate-pulse rounded bg-muted" />
        <div className="h-9 w-24 animate-pulse rounded-md bg-muted" />
      </div>
      <div className="h-4 w-full animate-pulse rounded bg-muted" />
      <div className="flex gap-[3px] overflow-hidden">
        {weeks.map((_, wi) => (
          <div key={wi} className="flex flex-col gap-[3px]">
            {rows.map((row) => (
              <motion.div
                key={row}
                className="h-[10px] w-[10px] animate-pulse rounded-[2px] bg-muted"
                initial={{ opacity: 0 }}
                animate={{ opacity: [0.4, 1, 0.4] }}
                transition={{ duration: 1.6, repeat: Infinity, delay: (wi + row) * 0.01 }}
              />
            ))}
          </div>
        ))}
      </div>
      <div className="flex justify-end">
        <div className="h-4 w-32 animate-pulse rounded bg-muted" />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    </div>
  );
}
