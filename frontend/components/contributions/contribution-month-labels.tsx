"use client";

import type { MonthLabel } from "@/lib/contributions";

const COLUMN_WIDTH = 13; // 10px cell + 3px gap

export function ContributionMonthLabels({
  labels,
  columnCount,
}: {
  labels: MonthLabel[];
  columnCount: number;
}) {
  return (
    <div
      className="relative h-4"
      style={{ width: columnCount * COLUMN_WIDTH }}
      aria-hidden="true"
    >
      {labels.map((m) => (
        <span
          key={m.index}
          className="absolute top-0 text-[10px] text-muted-foreground"
          style={{ left: m.index * COLUMN_WIDTH }}
        >
          {m.label}
        </span>
      ))}
    </div>
  );
}
