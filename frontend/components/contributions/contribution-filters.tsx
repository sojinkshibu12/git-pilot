"use client";

import type { ContributionType } from "@/lib/types";
import { cn } from "@/lib/utils";

export const CONTRIBUTION_FILTERS: { value: ContributionType; label: string }[] = [
  { value: "everything", label: "Everything" },
  { value: "commits", label: "Commits" },
  { value: "pull_requests", label: "Pull requests" },
  { value: "issues", label: "Issues" },
  { value: "reviews", label: "Reviews" },
  { value: "repositories", label: "Repositories" },
  { value: "actions", label: "Actions" },
];

interface ContributionFiltersProps {
  value: ContributionType;
  onChange: (value: ContributionType) => void;
}

export function ContributionFilters({ value, onChange }: ContributionFiltersProps) {
  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      role="group"
      aria-label="Contribution type"
    >
      {CONTRIBUTION_FILTERS.map((filter) => (
        <button
          key={filter.value}
          type="button"
          onClick={() => onChange(filter.value)}
          aria-pressed={value === filter.value}
          className={cn(
            "rounded-full px-3 py-1 text-xs font-medium transition-colors",
            value === filter.value
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground hover:bg-accent hover:text-foreground",
          )}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}
