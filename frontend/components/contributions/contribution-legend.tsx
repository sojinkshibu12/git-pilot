"use client";

const LEVELS = [0, 1, 2, 3, 4];

export function ContributionLegend() {
  return (
    <div
      className="flex items-center gap-1 text-[10px] text-muted-foreground"
      aria-label="Contribution intensity legend"
    >
      <span>Less</span>
      {LEVELS.map((level) => (
        <span
          key={level}
          className="h-[10px] w-[10px] rounded-[2px]"
          style={{ backgroundColor: `hsl(var(--contribution-${level}))` }}
        />
      ))}
      <span>More</span>
    </div>
  );
}
