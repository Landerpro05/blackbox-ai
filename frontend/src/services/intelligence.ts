import { request } from "./api";
import type {
  AICapabilities,
  AIAnalysis,
  AIAnalysisList,
  AICreate,
} from "../types/intelligence";

export const activeAI = (analysis: AIAnalysis) =>
  analysis.status === "pending" || analysis.status === "running";
export const intelligenceApi = {
  capabilities: (signal?: AbortSignal) =>
    request<AICapabilities>("/ai/capabilities", { signal }),
  list: (runId: string, offset: number, signal?: AbortSignal) =>
    request<AIAnalysisList>(
      `/runs/${encodeURIComponent(runId)}/ai-analysis?limit=5&offset=${offset}`,
      { signal },
    ),
  get: (id: string, signal?: AbortSignal) =>
    request<AIAnalysis>(`/ai-analyses/${encodeURIComponent(id)}`, { signal }),
  create: (runId: string, data: AICreate) =>
    request<AIAnalysis>(`/runs/${encodeURIComponent(runId)}/ai-analysis`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  cancel: (id: string) =>
    request<AIAnalysis>(`/ai-analyses/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
};
