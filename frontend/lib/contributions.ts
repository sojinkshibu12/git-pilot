import type { ContributionDay, ContributionType } from "@/lib/types";

export const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

/** Full month names for tooltips / statistics. */
export const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
/** Rows (0-6, Sun..Sat) that GitHub renders on the left gutter. */
export const GUTTER_ROWS = [0, 1, 2, 3, 4, 5, 6];

export function toISODate(d: Date): string {
  const y = d.getUTCFullYear();
  const m = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** GitHub-style intensity buckets: 0, 1-2, 3-5, 6-10, 10+. */
export function contributionLevel(count: number): 0 | 1 | 2 | 3 | 4 {
  if (count <= 0) return 0;
  if (count <= 2) return 1;
  if (count <= 5) return 2;
  if (count <= 10) return 3;
  return 4;
}

export function zeroDay(iso: string): ContributionDay {
  return {
    date: iso,
    count: 0,
    level: 0,
    commits: 0,
    pull_requests: 0,
    issues: 0,
    reviews: 0,
    repositories: 0,
    actions: 0,
  };
}

/** Per-day count for a given filter type. */
export function countForType(day: ContributionDay, type: ContributionType): number {
  switch (type) {
    case "everything":
      return day.count;
    case "commits":
      return day.commits;
    case "pull_requests":
      return day.pull_requests;
    case "issues":
      return day.issues;
    case "reviews":
      return day.reviews;
    case "repositories":
      return day.repositories;
    case "actions":
      return day.actions;
  }
}

/** First Sunday on or before a given UTC date (start of the heatmap grid). */
function sundayOnOrBefore(d: Date): Date {
  const s = new Date(d);
  s.setUTCDate(s.getUTCDate() - s.getUTCDay());
  return s;
}

/** Saturday on or after a given UTC date (end of the heatmap grid). */
function saturdayOnOrAfter(d: Date): Date {
  const s = new Date(d);
  s.setUTCDate(s.getUTCDate() + (6 - s.getUTCDay()));
  return s;
}

/**
 * Start of the rolling 12-month window that ends on `endISO`
 * (GitHub-profile style): 12 full calendar months ending today, sliding
 * forward as time passes.
 */
export function contributionWindowStart(endISO: string): string {
  const end = new Date(`${endISO}T00:00:00Z`);
  const start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 11, 1));
  return toISODate(start);
}

/**
 * Build the heatmap grid (columns = Sun..Sat weeks, GitHub layout) for the
 * range `startISO`..`endISO` (inclusive). Only days inside the range resolve
 * to a day object; leading/trailing padding cells are null.
 */
export function buildWeeks(
  startISO: string,
  endISO: string,
  days: ReadonlyMap<string, ContributionDay>,
): (ContributionDay | null)[][] {
  const start = new Date(`${startISO}T00:00:00Z`);
  const end = new Date(`${endISO}T00:00:00Z`);
  const gridStart = sundayOnOrBefore(start);
  const gridEnd = saturdayOnOrAfter(end);
  const weeks: (ContributionDay | null)[][] = [];
  const cursor = new Date(gridStart);
  while (cursor.getTime() <= gridEnd.getTime()) {
    const week: (ContributionDay | null)[] = [];
    for (let d = 0; d < 7; d++) {
      const iso = toISODate(cursor);
      if (iso < startISO || iso > endISO) {
        week.push(null);
      } else {
        week.push(days.get(iso) ?? zeroDay(iso));
      }
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    weeks.push(week);
  }
  return weeks;
}

export interface MonthLabel {
  index: number;
  label: string;
}

/** Month labels at the first column whose week contains the 1st of each month. */
export function monthLabelsForWeeks(
  startISO: string,
  endISO: string,
  weeks: (ContributionDay | null)[][],
): MonthLabel[] {
  const start = new Date(`${startISO}T00:00:00Z`);
  const gridStart = sundayOnOrBefore(start);
  const labels: MonthLabel[] = [];
  weeks.forEach((_, wi) => {
    for (let d = 0; d < 7; d++) {
      const day = new Date(gridStart);
      day.setUTCDate(day.getUTCDate() + wi * 7 + d);
      if (day.getUTCDate() !== 1) continue;
      const iso = toISODate(day);
      if (iso >= startISO && iso <= endISO) {
        labels.push({ index: wi, label: MONTHS[day.getUTCMonth()] });
      }
      break;
    }
  });
  return labels;
}

export function formatLongDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(undefined, {
    timeZone: "UTC",
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export function formatDay(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString(undefined, {
    timeZone: "UTC",
    month: "short",
    day: "numeric",
  });
}
