"use client";

import { useMemo, useState } from "react";

import {
  buildWeeks,
  contributionLevel,
  contributionWindowStart,
  countForType,
  monthLabelsForWeeks,
  toISODate,
} from "@/lib/contributions";
import { exportContributionPdf, exportContributionPng, exportContributionSvg } from "@/lib/export";
import type {
  ContributionResponse,
  ContributionStatistics,
  ContributionStreak,
  ContributionType,
} from "@/lib/types";
import { ContributionFilters } from "./contribution-filters";
import { ContributionHeatmap } from "./contribution-heatmap";
import { ContributionLegend } from "./contribution-legend";
import { ContributionSkeleton } from "./contribution-skeleton";
import { ContributionStatistics as StatisticsCards } from "./contribution-statistics";
import { ContributionYearSelector } from "./contribution-year-selector";

interface ContributionGraphProps {
  year: number;
  onYearChange: (year: number) => void;
  data?: ContributionResponse;
  statistics?: ContributionStatistics;
  streak?: ContributionStreak;
  isLoading: boolean;
  isRefreshing: boolean;
  isError?: boolean;
  error?: unknown;
  refreshError?: unknown;
  onRefresh: () => void;
}

export function ContributionGraph({
  year,
  onYearChange,
  data,
  statistics,
  streak,
  isLoading,
  isRefreshing,
  isError,
  error,
  refreshError,
  onRefresh,
}: ContributionGraphProps) {
  const [type, setType] = useState<ContributionType>("everything");
  const [exporting, setExporting] = useState<"svg" | "png" | "pdf" | null>(null);

  const currentYear = new Date().getFullYear();
  const isCurrentYear = year === currentYear;
  const endISO = useMemo(
    () => (isCurrentYear ? toISODate(new Date()) : `${year}-12-31`),
    [year, isCurrentYear],
  );
  const startISO = useMemo(
    () => (isCurrentYear ? contributionWindowStart(endISO) : `${year}-01-01`),
    [year, isCurrentYear, endISO],
  );

  const { weeks, labels } = useMemo(() => {
    if (!data) return { weeks: [], labels: [] };
    const filtered = new Map<string, ContributionResponse["days"][number]>();
    for (const day of data.days) {
      const count = type === "everything" ? day.count : countForType(day, type);
      filtered.set(day.date, { ...day, count, level: contributionLevel(count) });
    }
    const weeks = buildWeeks(startISO, endISO, filtered);
    return { weeks, labels: monthLabelsForWeeks(startISO, endISO, weeks) };
  }, [data, type, startISO, endISO]);

  if (isLoading || !data) {
    if (isError) {
      return (
        <div className="rounded-lg border border-border bg-card p-6 text-sm text-muted-foreground">
          Could not load contribution data.
          {error instanceof Error && <p className="mt-2 text-xs text-red-500 dark:text-red-400">{error.message}</p>}
          <button
            type="button"
            onClick={onRefresh}
            className="mt-4 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:opacity-90"
          >
            Try again
          </button>
        </div>
      );
    }
    return <ContributionSkeleton />;
  }

  if (!data.connected) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-lg border border-border bg-card p-8 text-center text-card-foreground">
        <p className="text-sm font-medium">No GitHub account connected</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          Connect your GitHub account in Security settings to see your contribution calendar.
        </p>
      </div>
    );
  }

  const exportSpec = { startISO, endISO, weeks };
  const exportButtons: { id: "svg" | "png" | "pdf"; label: string; run: () => Promise<void> | void }[] = [
    { id: "svg", label: "SVG", run: () => exportContributionSvg(exportSpec) },
    { id: "png", label: "PNG", run: () => exportContributionPng(exportSpec) },
    { id: "pdf", label: "PDF", run: () => exportContributionPdf(exportSpec) },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">Contributions</h2>
          <p className="text-xs text-muted-foreground">
            {data.total.toLocaleString()} total {isCurrentYear ? "in the last 12 months" : `in ${year}`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ContributionYearSelector value={year} onChange={onYearChange} />
          <div className="flex items-center gap-1">
            {exportButtons.map((btn) => (
              <button
                key={btn.id}
                type="button"
                disabled={exporting != null}
                onClick={async () => {
                  setExporting(btn.id);
                  try {
                    await btn.run();
                  } finally {
                    setExporting(null);
                  }
                }}
                className="h-9 rounded-md border border-border bg-background px-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
              >
                {exporting === btn.id ? "…" : btn.label}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            aria-label="Refresh contribution data"
            className="flex h-9 w-9 items-center justify-center rounded-md border border-border bg-background text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            >
              <path d="M21 12a9 9 0 1 1-2.64-6.36" />
              <path d="M21 3v6h-6" />
            </svg>
          </button>
        </div>
      </div>

      <ContributionFilters value={type} onChange={setType} />

      {refreshError ? (
        <p className="text-xs text-red-500 dark:text-red-400">
          Refresh failed. {refreshError instanceof Error ? refreshError.message : "Please try again."}
        </p>
      ) : null}

      <ContributionHeatmap weeks={weeks} labels={labels} />

      <div className="flex items-center justify-end">
        <ContributionLegend />
      </div>

      {statistics && streak && <StatisticsCards statistics={statistics} streak={streak} />}
    </div>
  );
}
