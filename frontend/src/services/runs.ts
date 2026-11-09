import { API_BASE_URL, request } from "./api";
import type {
  RunDetailData,
  RunLimits,
  RunList,
  TestIssue,
  TestPage,
  TestRun,
  TestingCapabilities,
} from "../types/api";

export const activeRun = (run: TestRun) =>
  run.status === "pending" || run.status === "running";
export const runLabels = {
  pending: "Pendiente",
  running: "En ejecución",
  completed: "Completado",
  failed: "Fallido",
  cancelled: "Cancelado",
};
export const evidenceUrl = (path: string) => `${API_BASE_URL}${path}`;

export const runsApi = {
  capabilities: (signal?: AbortSignal) =>
    request<TestingCapabilities>("/testing/capabilities", { signal }),
  list: (projectId: string | undefined, offset: number, signal?: AbortSignal) =>
    request<RunList>(
      `${projectId ? `/projects/${encodeURIComponent(projectId)}` : ""}/runs?limit=20&offset=${offset}`,
      { signal },
    ),
  start: (projectId: string, limits: RunLimits) =>
    request<TestRun>(`/projects/${encodeURIComponent(projectId)}/runs`, {
      method: "POST",
      body: JSON.stringify({ authorize_demo: true, limits }),
    }),
  get: (id: string, signal?: AbortSignal) =>
    request<TestRun>(`/runs/${encodeURIComponent(id)}`, { signal }),
  cancel: (id: string) =>
    request<TestRun>(`/runs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  async details(id: string, signal?: AbortSignal): Promise<RunDetailData> {
    const path = `/runs/${encodeURIComponent(id)}`;
    // Read the state before its collections, so a terminal run has all its results.
    const run = await request<TestRun>(path, { signal });
    const [issues, pages] = await Promise.all([
      request<TestIssue[]>(`${path}/issues`, { signal }),
      request<TestPage[]>(`${path}/pages`, { signal }),
    ]);
    return { run, issues, pages };
  },
};
