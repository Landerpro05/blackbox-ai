import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileBarChart2 } from "lucide-react";
import { useResource } from "../hooks/useResource";
import {
  reportingApi,
  severityLabels,
  type ExportFormat,
} from "../services/reporting";
import { ResourceError, ResourceLoading } from "./ResourceFeedback";

export function ReportPanel({ runId }: { runId: string }) {
  const loader = useCallback(
    (signal: AbortSignal) => reportingApi.report(runId, signal),
    [runId],
  );
  const { state, reload } = useResource(loader);
  const [evidence, setEvidence] = useState(false);
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const download = async (format: ExportFormat) => {
    controller.current = new AbortController();
    setBusy(format);
    setNotice("");
    setError("");
    try {
      await reportingApi.download(
        runId,
        format,
        evidence,
        controller.current.signal,
      );
      setNotice(`Informe ${format.toUpperCase()} preparado para descargar.`);
    } catch (caught) {
      if (!controller.current.signal.aborted)
        setError(
          caught instanceof Error
            ? caught.message
            : "No se pudo generar el informe.",
        );
    } finally {
      setBusy(null);
    }
  };
  return (
    <section
      className="panel reporting-panel"
      aria-label="Informe de ejecución"
    >
      <div className="panel-heading">
        <div>
          <h2>
            <FileBarChart2 size={18} /> Informe de ejecución
          </h2>
          <p>Resultados persistidos · Exportación sin conexión</p>
        </div>
      </div>
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : (
        <>
          <div className="severity-summary">
            {Object.entries(state.data.summary.by_severity).map(
              ([key, value]) => (
                <div key={key}>
                  <span className={`status-pill severity-${key}`}>
                    {severityLabels[key as keyof typeof severityLabels]}
                  </span>
                  <strong>{value}</strong>
                </div>
              ),
            )}
          </div>
          <dl className="report-facts">
            <div>
              <dt>Errores HTTP</dt>
              <dd>{state.data.summary.http_errors}</dd>
            </div>
            <div>
              <dt>JavaScript / consola</dt>
              <dd>{state.data.summary.javascript_errors}</dd>
            </div>
            <div>
              <dt>Enlaces rotos</dt>
              <dd>{state.data.summary.broken_links}</dd>
            </div>
            <div>
              <dt>Navegación media</dt>
              <dd>
                {state.data.summary.average_navigation_ms === null
                  ? "Sin datos"
                  : `${state.data.summary.average_navigation_ms} ms`}
              </dd>
            </div>
          </dl>
          {state.data.warnings.map((warning) => (
            <p className="report-note" key={warning}>
              {warning}
            </p>
          ))}
          {(state.data.omitted.issues > 0 || state.data.omitted.pages > 0) && (
            <p role="status">
              Detalles omitidos: {state.data.omitted.issues} incidencias,{" "}
              {state.data.omitted.pages} páginas.
            </p>
          )}
          <label className="evidence-option">
            <input
              type="checkbox"
              checked={evidence}
              onChange={(event) => setEvidence(event.target.checked)}
            />{" "}
            Incluir capturas en HTML y PDF (hasta 4)
          </label>
          <div className="export-actions">
            {(["html", "pdf", "json", "csv"] as const).map((format) => (
              <button
                className="button-secondary"
                disabled={busy !== null}
                key={format}
                onClick={() => void download(format)}
              >
                <Download size={14} />
                {busy === format
                  ? "Preparando…"
                  : `Descargar ${format.toUpperCase()}`}
              </button>
            ))}
          </div>
        </>
      )}
      {notice && (
        <p className="inline-alert success-alert" role="status">
          {notice}
        </p>
      )}
      {error && (
        <p className="inline-alert error-alert" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
