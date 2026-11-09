export interface AICapabilities {
  rules_enabled: boolean;
  llm_enabled: boolean;
  provider: string;
  model: string;
  external_confirmation_required: boolean;
  screenshots_sent: boolean;
  max_context_bytes: number;
  max_findings: number;
  max_output_tokens: number;
  max_attempts: number;
  daily_call_limit: number;
  daily_token_limit: number;
  daily_budget_usd: number | null;
  prices_configured: boolean;
  test_execution_enabled: false;
}
export interface AIFinding {
  hypothesis: string;
  confidence: "low" | "medium" | "high";
  evidence_ids: string[];
  diagnostic_steps: string[];
  recommendations: string[];
  limitations: string[];
}
export interface AITest {
  template: string;
  objective: string;
  evidence_ids: string[];
  preconditions: string[];
  actions: string[];
  assertions: string[];
  limitations: string[];
  code: string;
}
export interface AIAnalysis {
  id: string;
  run_id: string;
  mode: "rules" | "llm";
  mode_label: string;
  provider: string;
  model: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  prompt_version: string;
  created_at: string;
  completed_at: string | null;
  external_authorized_at: string | null;
  error_message: string | null;
  estimated_input_tokens: number;
  estimated_output_tokens: number;
  reserved_tokens: number;
  reserved_cost_usd: string | null;
  actual_input_tokens: number | null;
  actual_output_tokens: number | null;
  evidence: {
    run_id: string;
    run_status: string;
    target_url: string;
    summary: {
      pages: number;
      issues: number;
      average_navigation_ms: number | null;
    };
    issues: {
      id: string;
      type: string;
      severity: string;
      title: string;
      message: string;
      url: string;
      screenshot_page_id: string | null;
      quarantined: boolean;
    }[];
    pages: {
      id: string;
      url: string;
      status_code: number | null;
      load_time_ms: number;
      screenshot_available: boolean;
    }[];
    groups: {
      fingerprint: string;
      evidence_ids: string[];
      count: number;
      source: "deterministic";
    }[];
    omitted_issues: number;
    omitted_pages: number;
    quarantined_messages: number;
    history: {
      id: string;
      base_run_id: string;
      counts: Record<string, number>;
      partial: boolean;
    } | null;
  };
  result: {
    summary: string;
    findings: AIFinding[];
    recommendations: string[];
    suggested_tests: AITest[];
    hypothetical_relations: { hypothesis: string; evidence_ids: string[] }[];
    limitations: string[];
  } | null;
}
export interface AIAnalysisList {
  items: AIAnalysis[];
  total: number;
  limit: number;
  offset: number;
}
export interface AICreate {
  mode: "rules" | "llm";
  authorize_external: boolean;
  max_findings: number;
  include_history: boolean;
  consent_provider: string | null;
  consent_model: string | null;
}
