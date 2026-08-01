"use client";

import { motion } from "framer-motion";
import { useCallback, useRef, useState } from "react";

import type { MonthLabel } from "@/lib/contributions";
import { GUTTER_ROWS, WEEKDAY_LABELS } from "@/lib/contributions";
import type { ContributionDay } from "@/lib/types";
import { ContributionCell, type HoverCell } from "./contribution-cell";
import { ContributionMonthLabels } from "./contribution-month-labels";
import { ContributionTooltip } from "./contribution-tooltip";

const CELL = 10;
const GAP = 3;
const COLUMN_WIDTH = CELL + GAP;
const GUTTER_WIDTH = 26;
const TOOLTIP_WIDTH = 200;
const TOOLTIP_HEIGHT = 56;

interface ContributionHeatmapProps {
  weeks: (ContributionDay | null)[][];
  labels: MonthLabel[];
}

export function ContributionHeatmap({ weeks, labels }: ContributionHeatmapProps) {
  const [hover, setHover] = useState<{ day: ContributionDay; x: number; y: number } | null>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  const handleHover = useCallback((cell: HoverCell | null) => {
    if (!cell) {
      setHover(null);
      return;
    }
    let x = Math.min(cell.rect.left + 4, window.innerWidth - TOOLTIP_WIDTH - 8);
    if (x < 8) x = 8;
    let y = cell.rect.top - TOOLTIP_HEIGHT - 10;
    if (y < 8) y = cell.rect.bottom + 10;
    setHover({ day: cell.day, x, y });
  }, []);

  return (
    <div
      ref={scrollerRef}
      role="region"
      aria-label="Contribution calendar"
      className="w-fit max-w-full overflow-x-auto rounded-xl border border-border bg-card p-3 pb-2"
    >
      <div className="min-w-max">
        <div className="flex">
          <div className="w-[26px] shrink-0" />
          <ContributionMonthLabels labels={labels} columnCount={weeks.length} />
        </div>
        <div className="mt-1 flex">
          <div
            className="relative h-[88px] w-[26px] shrink-0 pr-1 text-right text-[9px] leading-none text-muted-foreground"
            aria-hidden="true"
          >
            {GUTTER_ROWS.map((row) => (
              <span
                key={row}
                className="absolute right-1"
                style={{ top: row * COLUMN_WIDTH + 1 }}
              >
                {WEEKDAY_LABELS[row]}
              </span>
            ))}
          </div>
          <div className="flex gap-[3px]">
            {weeks.map((week, wi) => (
              <motion.div
                key={wi}
                className="flex flex-col gap-[3px]"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: wi * 0.012, duration: 0.35 }}
              >
                {week.map((day, row) => (
                  <ContributionCell key={row} day={day} onHover={handleHover} />
                ))}
              </motion.div>
            ))}
          </div>
        </div>
      </div>
      {hover && (
        <ContributionTooltip key={hover.day.date} day={hover.day} x={hover.x} y={hover.y} />
      )}
    </div>
  );
}
