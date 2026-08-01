export interface UserProfile {
  id: string;
  email: string | null;
  email_verified: boolean;
  display_name: string | null;
  avatar_url: string | null;
  locale: string;
  plan: string;
  mfa_enabled: boolean;
  created_at: string;
}

export interface SessionInfo {
  id: string;
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  ip_address: string | null;
  user_agent: string | null;
  device_label: string | null;
  is_current: boolean;
  status: string;
}

export interface ConnectedAccount {
  provider: "github" | "email" | "google" | "microsoft" | "gitlab";
  connected: boolean;
  primary: boolean;
  display_name?: string | null;
  github_id?: number | null;
  login?: string | null;
  avatar_url?: string | null;
  email?: string | null;
  email_verified?: boolean;
}

export interface SecurityOverview {
  has_password: boolean;
  mfa_enabled: boolean;
  email_verified: boolean;
  connected_accounts: ConnectedAccount[];
  active_sessions_count: number;
}

export interface Repository {
  id: number;
  name: string;
  full_name: string;
  private: boolean;
  html_url: string;
  description: string | null;
  language: string | null;
  default_branch: string;
  stargazers_count: number;
  forks_count: number;
  open_issues_count: number;
  visibility: string;
  contributions?: number | null;
}

export interface RepoListResponse {
  repositories: Repository[];
  page: number;
  per_page: number;
  total_count: number;
  total_pages: number;
}

export interface ContributionSummary {
  commits: number;
  pull_requests: number;
  issues: number;
  reviews: number;
  total: number;
}

export type ContributionType =
  | "everything"
  | "commits"
  | "pull_requests"
  | "issues"
  | "reviews"
  | "repositories"
  | "actions";

export interface ContributionDay {
  date: string; // YYYY-MM-DD
  count: number;
  level: 0 | 1 | 2 | 3 | 4;
  commits: number;
  pull_requests: number;
  issues: number;
  reviews: number;
  repositories: number;
  actions: number;
}

export interface ContributionBreakdown {
  commits: number;
  pull_requests: number;
  issues: number;
  reviews: number;
  repositories: number;
  actions: number;
}

export interface ContributionResponse {
  year: number;
  connected: boolean;
  days: ContributionDay[];
  total: number;
  max: number;
  breakdown: ContributionBreakdown;
}

export interface ContributionStreak {
  current_streak: number;
  longest_streak: number;
  current_streak_end: string | null;
}

export interface ContributionStatistics {
  total: number;
  days_contributed: number;
  average_per_day: number;
  most_active_month: number | null;
  most_active_month_contributions: number;
  most_active_weekday: number | null;
  most_active_weekday_contributions: number;
  most_active_repository: { full_name: string; contributions: number } | null;
  breakdown: ContributionBreakdown;
}
