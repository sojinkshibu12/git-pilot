"use client";

import { MONTH_NAMES } from "@/lib/contributions";
import type { ContributionStatistics, ContributionStreak } from "@/lib/types";

const FULL_WEEKDAYS = [
  "Sunday",
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
];

interface ContributionStatisticsProps {
  statistics: ContributionStatistics;
  streak: ContributionStreak;
}

export function ContributionStatistics({ statistics, streak }: ContributionStatisticsProps) {
  const items: { label: string; value: string }[] = [
    { label: "Current streak", value: `${streak.current_streak} day${streak.current_streak === 1 ? "" : "s"}` },
    { label: "Longest streak", value: `${streak.longest_streak} day${streak.longest_streak === 1 ? "" : "s"}` },
    { label: "Total", value: statistics.total.toLocaleString() },
    { label: "Days contributed", value: statistics.days_contributed.toLocaleString() },
    { label: "Average / day", value: statistics.average_per_day.toLocaleString() },
    {
      label: "Most active month",
      value:
        statistics.most_active_month != null
          ? MONTH_NAMES[statistics.most_active_month - 1] ?? "—"
          : "—",
    },
    {
      label: "Most active weekday",
      value:
        statistics.most_active_weekday != null
          ? FULL_WEEKDAYS[statistics.most_active_weekday] ?? "—"
          : "—",
    },
    {
      label: "Most active repo",
      value: statistics.most_active_repository?.full_name ?? "—",
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Contribution statistics">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-lg border border-border bg-card p-3 text-card-foreground"
        >
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{item.label}</p>
          <p className="mt-1 truncate text-sm font-semibold" title={item.value}>
            {item.value}
          </p>
        </div>
      ))}
    </div>
  );
}
