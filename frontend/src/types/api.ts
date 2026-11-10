export type RunStatus =
  "queued" | "running" | "completed" | "failed" | "cancelled";

export interface ProjectInput {
  name: string;
  description: string;
  base_url: string;
}

export interface Project extends ProjectInput {
  id: string;
  max_pages: number;
  max_depth: number;
  max_duration_seconds: number;
  created_at: string;
  updated_at: string;
}

export interface ProjectList {
  items: Project[];
  total: number;
  limit: number;
  offset: number;
}

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
  database: "connected";
}

export interface DashboardResponse {
  metrics: {
    projects: number;
    runs: number;
    issues: number;
    critical_issues: number;
    active_runs: number;
  };
  trend: { date: string; runs: number; issues: number }[];
  recent_runs: {
    id: string;
    project_name: string;
    status: RunStatus;
    pages_visited: number;
    issue_count: number;
    created_at: string;
  }[];
  projects: { id: string; name: string; base_url: string; run_count: number }[];
  generated_at: string;
}

export type AnalysisStatus =
  "pending" | "running" | "completed" | "failed" | "cancelled";
export interface RunLimits {
  max_pages: number;
  max_depth: number;
  navigation_timeout_seconds: number;
  timeout_seconds: number;
  max_requests: number;
}
export interface TestingCapabilities {
  mode: "controlled_demo";
  demo_enabled: boolean;
  remote_enabled: false;
  demo_url: string;
  defaults: RunLimits;
  maximums: RunLimits;
}
export interface TestRun {
  target_url?: string;
  suite_id?: string | null;
  environment_snapshot?: Record<string, string>;
  id: string;
  project_id: string;
  status: AnalysisStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  pages_scanned: number;
  issues_found: number;
  request_count: number;
  duration_ms: number;
  error_message: string | null;
  cancellation_requested: boolean;
  limits: RunLimits;
}
export interface RunList {
  items: TestRun[];
  total: number;
  limit: number;
  offset: number;
}
export interface TestIssue {
  id: string;
  test_run_id: string;
  type: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  title: string;
  description: string;
  url: string;
  evidence_url: string | null;
  created_at: string;
}
export interface TestPage {
  id: string;
  test_run_id: string;
  url: string;
  status_code: number | null;
  load_time_ms: number;
  depth: number;
  screenshot_url: string | null;
  scanned_at: string;
}
export interface RunDetailData {
  run: TestRun;
  issues: TestIssue[];
  pages: TestPage[];
}
