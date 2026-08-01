"use client";

import { motion } from "framer-motion";

import { formatLongDate } from "@/lib/contributions";
import type { ContributionDay } from "@/lib/types";

interface ContributionTooltipProps {
  day: ContributionDay;
  x: number;
  y: number;
}

export function ContributionTooltip({ day, x, y }: ContributionTooltipProps) {
  const count = day.count;
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.85, y: 4 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.12 }}
      role="status"
      className="pointer-events-none fixed z-50 rounded-lg border border-border bg-popover px-3 py-2 text-popover-foreground shadow-xl"
      style={{ left: x, top: y }}
    >
      <p className="text-sm font-semibold">
        {count === 0 ? "No contributions" : `${count} contribution${count === 1 ? "" : "s"}`}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">{formatLongDate(day.date)}</p>
    </motion.div>
  );
}
