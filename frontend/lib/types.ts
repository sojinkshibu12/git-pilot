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

// ── Repository detail (GitHub gateway) ───────────────────────────────────────

export interface GHUserLite {
  id: number;
  login: string;
  name?: string | null;
  avatar_url?: string | null;
  html_url?: string | null;
  email?: string | null;
  type?: string;
  site_admin?: boolean;
  bio?: string | null;
  location?: string | null;
}

export interface CommitAuthor {
  name?: string | null;
  email?: string | null;
  date?: string | null;
}

export interface CommitFileData {
  filename: string;
  status: string;
  additions: number;
  deletions: number;
  changes: number;
  raw_url?: string | null;
  blob_url?: string | null;
  previous_filename?: string | null;
  patch?: string | null;
}

export interface CommitData {
  sha: string;
  node_id?: string | null;
  message?: string | null;
  url?: string | null;
  html_url?: string | null;
  commit?: {
    message?: string;
    author?: CommitAuthor | null;
    committer?: CommitAuthor | null;
  } | null;
  author?: GHUserLite | CommitAuthor | null;
  committer?: GHUserLite | CommitAuthor | null;
  parents?: { sha: string; url?: string }[];
  files?: CommitFileData[];
}

export interface BranchData {
  name: string;
  protected: boolean;
  commit?: { sha?: string; url?: string } | null;
}

export interface PullRequestData {
  id: number;
  number: number;
  state: string;
  title: string;
  body?: string | null;
  html_url: string;
  diff_url?: string | null;
  patch_url?: string | null;
  mergeable?: boolean | null;
  merged: boolean;
  mergeable_state?: string | null;
  head?: { label?: string; ref?: string; sha?: string } | null;
  base?: { label?: string; ref?: string; sha?: string } | null;
  user?: GHUserLite | null;
  created_at?: string | null;
  updated_at?: string | null;
  merged_at?: string | null;
}

export interface IssueLabel {
  id?: number;
  name: string;
  color?: string;
  description?: string | null;
  default?: boolean;
}

export interface IssueData {
  id: number;
  number: number;
  state: string;
  title: string;
  body?: string | null;
  html_url: string;
  user?: GHUserLite | null;
  assignees?: (GHUserLite | Record<string, unknown>)[] | null;
  labels?: (IssueLabel | Record<string, unknown>)[] | null;
  comments: number;
  pull_request?: Record<string, unknown> | null;
  repository?: { full_name?: string; name?: string; html_url?: string } | null;
  created_at?: string | null;
  updated_at?: string | null;
  closed_at?: string | null;
}

export interface ReleaseData {
  id: number;
  tag_name: string;
  name?: string | null;
  body?: string | null;
  draft: boolean;
  prerelease: boolean;
  html_url?: string | null;
  published_at?: string | null;
}

export interface WorkflowRunData {
  id: number;
  name?: string | null;
  head_branch?: string | null;
  head_sha?: string | null;
  status?: string | null;
  conclusion?: string | null;
  run_number: number;
  event?: string | null;
  html_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkflowData {
  id: number;
  name: string;
  path: string;
  state?: string | null;
  html_url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface LabelData {
  id: number;
  name: string;
  color: string;
  description?: string | null;
  default: boolean;
}

export interface MilestoneData {
  id: number;
  number: number;
  title: string;
  description?: string | null;
  state: string;
  open_issues: number;
  closed_issues: number;
  created_at?: string | null;
  due_on?: string | null;
}

export interface TeamData {
  id: number;
  name: string;
  slug: string;
  description?: string | null;
  privacy?: string | null;
  permission?: string | null;
}

export interface BranchesResponse {
  branches: BranchData[];
}

export interface CommitsResponse {
  commits: CommitData[];
}

export interface PullRequestsResponse {
  pull_requests: PullRequestData[];
}

export interface IssuesResponse {
  issues: IssueData[];
}

export interface AssignedIssuesResponse {
  issues: IssueData[];
}

export interface ReleasesResponse {
  releases: ReleaseData[];
}

export interface WorkflowRunsResponse {
  workflow_runs: WorkflowRunData[];
}

export interface WorkflowsResponse {
  workflows: WorkflowData[];
}

export interface LabelsResponse {
  labels: LabelData[];
}

export interface MilestonesResponse {
  milestones: MilestoneData[];
}

export interface CollaboratorsResponse {
  collaborators: GHUserLite[];
}

export interface TeamsResponse {
  teams: TeamData[];
}
