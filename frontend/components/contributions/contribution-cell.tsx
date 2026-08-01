"use client";

import { memo } from "react";

import type { ContributionDay } from "@/lib/types";
import { cn } from "@/lib/utils";

export interface HoverCell {
  day: ContributionDay;
  rect: DOMRect;
}

interface ContributionCellProps {
  day: ContributionDay | null;
  onHover: (cell: HoverCell | null) => void;
}

export const ContributionCell = memo(function ContributionCell({
  day,
  onHover,
}: ContributionCellProps) {
  if (!day) {
    return (
      <div
        aria-hidden="true"
        style={{ backgroundColor: "hsl(var(--contribution-0) / 0.45)" }}
        className="h-[10px] w-[10px] rounded-[2px]"
      />
    );
  }
  const label = `${
    day.count === 0 ? "No contributions" : `${day.count} contribution${day.count === 1 ? "" : "s"}`
  } on ${day.date}`;
  return (
    <div
      role="img"
      aria-label={label}
      tabIndex={0}
      data-date={day.date}
      data-count={day.count}
      style={{ backgroundColor: `hsl(var(--contribution-${day.level}))` }}
      className={cn(
        "h-[10px] w-[10px] rounded-[2px] outline-none transition-transform duration-100 hover:scale-125 focus-visible:ring-2 focus-visible:ring-ring",
      )}
      onMouseEnter={(e) => onHover({ day, rect: e.currentTarget.getBoundingClientRect() })}
      onMouseLeave={() => onHover(null)}
      onFocus={(e) => onHover({ day, rect: e.currentTarget.getBoundingClientRect() })}
      onBlur={() => onHover(null)}
    />
  );
});
