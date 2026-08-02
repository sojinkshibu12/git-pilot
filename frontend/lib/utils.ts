import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "just now";
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day}d ago`;
  return new Date(iso).toLocaleDateString();
}

export function truncate(s: string, n: number): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

export function shortSha(sha: string): string {
  return sha.length > 7 ? sha.slice(0, 7) : sha;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Extract an ISO date string from a GitHub author/committer object (either a
 * GHUserLite or an inline { name, email, date } commit-author shape). */
export function commitAuthorDate(
  author:
    | { date?: string | null; name?: string | null }
    | ({ login?: string; avatar_url?: string | null } & Record<string, unknown>)
    | null
    | undefined,
): string | null {
  if (!author || typeof author !== "object") return null;
  const d = (author as { date?: string | null }).date;
  return d ?? null;
}

/** Extract a display name from a GitHub author/committer object. */
export function commitAuthorName(
  author:
    | { login?: string; name?: string | null; email?: string | null }
    | { login?: string }
    | null
    | undefined,
): string {
  if (!author || typeof author !== "object") return "unknown";
  return (author as { login?: string }).login ?? (author as { name?: string | null }).name ?? "unknown";
}
