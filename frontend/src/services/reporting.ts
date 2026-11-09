import { request, requestResponse } from "./api";
import type { Analytics, Comparison, RunReport } from "../types/reporting";

export const severityLabels = {
  info: "Informativa",
  low: "Baja",
  medium: "Media",
  high: "Alta",
  critical: "Crítica",
};
export const classificationLabels = {
  NEW: "Nuevas",
  RESOLVED: "Resueltas",
  PERSISTENT: "Persistentes",
  UNCONFIRMED: "Sin confirmar",
};
export type ExportFormat = "html" | "pdf" | "json" | "csv";

export const reportingApi = {
  report: (id: string, signal?: AbortSignal) =>
    request<RunReport>(`/runs/${encodeURIComponent(id)}/report`, { signal }),
  analytics: (project: string, offset: number, signal?: AbortSignal) =>
    request<Analytics>(
      `/projects/${encodeURIComponent(project)}/analytics?limit=20&offset=${offset}`,
      { signal },
    ),
  compare: (
    project: string,
    base: string,
    target: string,
    signal?: AbortSignal,
  ) =>
    request<Comparison>(
      `/projects/${encodeURIComponent(project)}/compare?base_run_id=${encodeURIComponent(base)}&target_run_id=${encodeURIComponent(target)}`,
      { signal },
    ),
  async download(
    id: string,
    format: ExportFormat,
    evidence: boolean,
    signal: AbortSignal,
  ) {
    const type = format === "html" || format === "pdf" ? "report" : "export";
    const response = await requestResponse(
      `/runs/${encodeURIComponent(id)}/${type}/${format}?include_evidence=${evidence}`,
      { signal, headers: { Accept: "*/*" } },
      60_000,
    );
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `blackbox-${id}.${format}`;
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
