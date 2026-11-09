import type { TestIssue } from "./api";

export interface ReportSummary {
  pages: number;
  issues: number;
  by_severity: Record<TestIssue["severity"], number>;
  by_type: Record<string, number>;
  http_errors: number;
  javascript_errors: number;
  broken_links: number;
  average_navigation_ms: number | null;
}
export interface ReportIssue {
  id: string;
  type: string;
  severity: TestIssue["severity"];
  title: string;
  description: string;
  url: string;
  reproduction_steps: string | null;
  evidence_page_id: string | null;
}
export interface RunReport {
  summary: ReportSummary;
  warnings: string[];
  omitted: { issues: number; pages: number };
}
export type Classification = "NEW" | "RESOLVED" | "PERSISTENT" | "UNCONFIRMED";
export interface Regression {
  base_run_id: string;
  target_run_id: string;
  counts: Record<Classification, number>;
  partial: boolean;
  heuristic: string;
}
export interface Comparison extends Regression {
  items: {
    fingerprint: string;
    classification: Classification;
    issue: ReportIssue;
  }[];
  warnings: string[];
  omitted: {
    base: { issues: number; pages: number };
    target: { issues: number; pages: number };
  };
}
export interface Analytics {
  total_runs: number;
  total_issues: number;
  by_severity: ReportSummary["by_severity"];
  by_type: { type: string; count: number }[];
  types_truncated: boolean;
  average_navigation_ms: number | null;
  items: {
    id: string;
    created_at: string;
    status: string;
    issues: number;
    average_navigation_ms: number | null;
  }[];
  limit: number;
  offset: number;
  regression: Regression | null;
}
