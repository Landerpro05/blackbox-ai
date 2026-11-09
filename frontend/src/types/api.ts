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
