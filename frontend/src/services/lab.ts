import { request } from "./api";
import type { RunLimits, TestRun } from "../types/api";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}
export interface EnvironmentInput {
  name: string;
  kind: "demo" | "local";
  base_url: string;
  limits: RunLimits;
}
export interface Environment extends EnvironmentInput {
  id: string;
  authorized_origin: string;
  configuration_state: string;
  last_check_status: string | null;
  last_checked_at: string | null;
}
export interface Suite {
  id: string;
  project_id: string;
  name: string;
  description: string;
}
export type CaseType =
  | "http_status"
  | "title"
  | "element_exists"
  | "text_visible"
  | "no_js_errors"
  | "internal_links"
  | "navigate";
export interface Definition {
  type: CaseType;
  path: string;
  minimum?: number;
  maximum?: number;
  expected_title?: string;
  selector?: string;
  text?: string;
  destination?: string;
}
export interface SuiteCase {
  id: string;
  name: string;
  position: number;
  enabled: boolean;
  definition: Definition;
}
export interface SuiteDetail extends Suite {
  cases: SuiteCase[];
}
export interface SuiteResults {
  run: TestRun;
  environment: Record<string, string>;
  counts: Record<"pending" | "pass" | "fail" | "error" | "skipped", number>;
  cases: {
    id: string;
    name: string;
    position: number;
    definition: Definition;
    status: string;
    message: string;
    duration_ms: number;
    evidence_url: string | null;
  }[];
}
export interface LabCapabilities {
  local_enabled: boolean;
  demo_enabled: boolean;
  allowed_origins: string[];
  ci_status: string;
  workflow_path: string;
}
const send = <T>(path: string, method: string, data?: unknown) =>
  request<T>(path, {
    method,
    ...(data === undefined ? {} : { body: JSON.stringify(data) }),
  });
export const labApi = {
  capabilities: (signal?: AbortSignal) =>
    request<LabCapabilities>("/lab/capabilities", { signal }),
  environments: (project: string, offset = 0, signal?: AbortSignal) =>
    request<Page<Environment>>(
      `/projects/${project}/environments?limit=20&offset=${offset}`,
      { signal },
    ),
  saveEnvironment: (project: string, data: EnvironmentInput, id?: string) =>
    send<Environment>(
      id ? `/environments/${id}` : `/projects/${project}/environments`,
      id ? "PATCH" : "POST",
      data,
    ),
  deleteEnvironment: (id: string) =>
    send<void>(`/environments/${id}`, "DELETE"),
  checkEnvironment: (environment: Environment) =>
    send<Environment>(`/environments/${environment.id}/check`, "POST", {
      authorize: true,
      consent_origin: environment.authorized_origin,
    }),
  suites: (project: string, offset = 0, signal?: AbortSignal) =>
    request<Page<Suite>>(
      `/projects/${project}/suites?limit=20&offset=${offset}`,
      { signal },
    ),
  suite: (id: string, signal?: AbortSignal) =>
    request<SuiteDetail>(`/suites/${id}`, { signal }),
  saveSuite: (
    project: string,
    data: { name: string; description: string },
    id?: string,
  ) =>
    send<Suite>(
      id ? `/suites/${id}` : `/projects/${project}/suites`,
      id ? "PATCH" : "POST",
      data,
    ),
  deleteSuite: (id: string) => send<void>(`/suites/${id}`, "DELETE"),
  saveCase: (suite: string, data: Omit<SuiteCase, "id">, id?: string) =>
    send<SuiteCase>(
      id ? `/suite-cases/${id}` : `/suites/${suite}/cases`,
      id ? "PATCH" : "POST",
      data,
    ),
  toggleCase: (id: string, enabled: boolean) =>
    send<SuiteCase>(`/suite-cases/${id}`, "PATCH", { enabled }),
  deleteCase: (id: string) => send<void>(`/suite-cases/${id}`, "DELETE"),
  importAI: (suite: string, data: unknown) =>
    send<SuiteCase>(`/suites/${suite}/import-ai`, "POST", data),
  start: (suite: string, environment: Environment) =>
    send<TestRun>(`/suites/${suite}/runs`, "POST", {
      environment_id: environment.id,
      authorize: true,
      consent_origin: environment.authorized_origin,
    }),
  history: (suite: string, offset: number, signal?: AbortSignal) =>
    request<Page<TestRun>>(`/suites/${suite}/runs?limit=20&offset=${offset}`, {
      signal,
    }),
  results: (run: string, signal?: AbortSignal) =>
    request<SuiteResults>(`/runs/${run}/suite-results`, { signal }),
};
export const caseLabels: Record<CaseType, string> = {
  http_status: "Estado HTTP",
  title: "Título de página",
  element_exists: "Existencia de elemento",
  text_visible: "Texto visible",
  no_js_errors: "Sin errores JavaScript",
  internal_links: "Enlaces internos",
  navigate: "Navegación autorizada",
};
