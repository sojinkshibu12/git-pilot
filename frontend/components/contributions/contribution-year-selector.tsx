"use client";

import { useMemo } from "react";

interface ContributionYearSelectorProps {
  value: number;
  onChange: (year: number) => void;
  minYear?: number;
}

export function ContributionYearSelector({
  value,
  onChange,
  minYear = 2023,
}: ContributionYearSelectorProps) {
  const years = useMemo(() => {
    const current = new Date().getFullYear();
    return Array.from({ length: current - minYear + 1 }, (_, i) => current - i);
  }, [minYear]);

  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="sr-only">Contribution year</span>
      <select
        aria-label="Contribution year"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-9 rounded-md border border-border bg-background px-3 text-sm font-medium text-foreground outline-none transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring"
      >
        {years.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </label>
  );
}
