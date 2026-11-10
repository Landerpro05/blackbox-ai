import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { usePollingResource } from "../hooks/usePollingResource";
import { labApi, type SuiteResults as Results } from "../services/lab";
import { activeRun, evidenceUrl } from "../services/runs";
import { ResourceError, ResourceLoading } from "./ResourceFeedback";

const polling = (data: Results) => activeRun(data.run);
export function SuiteResults({ runId }: { runId: string }) {
  const loader = useCallback(
    (signal: AbortSignal) => labApi.results(runId, signal),
    [runId],
  );
  const { state, reload } = usePollingResource(loader, polling);
  const [failures, setFailures] = useState(false);
  if (state.status === "loading")
    return <ResourceLoading label="Cargando casos de la suite…" />;
  if (state.status === "error")
    return <ResourceError message={state.message} onRetry={reload} />;
  const data = state.data;
  return (
    <section className="panel lab-section" aria-label="Resultados de la suite">
      <div className="panel-heading">
        <div>
          <h2>{data.environment.suite_name || "Suite"}</h2>
          <p>
            {data.environment.name} · {data.environment.base_url}
          </p>
        </div>
        <Link to={`/lab?project=${data.run.project_id}`}>
          Volver a Testing Lab
        </Link>
      </div>
      <div className="lab-counts" aria-live="polite">
        {Object.entries(data.counts).map(([key, count]) => (
          <span
            className={`status-pill ${key === "pass" ? "green" : key === "fail" || key === "error" ? "red" : "neutral"}`}
            key={key}
          >
            {key}: {count}
          </span>
        ))}
      </div>
      <label className="lab-checkbox">
        <input
          type="checkbox"
          checked={failures}
          onChange={(e) => setFailures(e.target.checked)}
        />
        Mostrar solo fallos y errores
      </label>
      <div className="lab-list">
        {data.cases
          .filter((c) => !failures || ["fail", "error"].includes(c.status))
          .map((c) => (
            <article className="lab-row" key={c.id}>
              <div>
                <strong>
                  {c.position + 1}. {c.name}
                </strong>
                <p>
                  {c.definition.path} · {c.message || "Esperando ejecución"}
                </p>
                <small>{c.duration_ms} ms</small>
              </div>
              <span
                className={`status-pill ${c.status === "pass" ? "green" : ["fail", "error"].includes(c.status) ? "red" : "neutral"}`}
              >
                {c.status}
              </span>
              {c.evidence_url && (
                <a
                  href={evidenceUrl(c.evidence_url)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Evidencia
                </a>
              )}
            </article>
          ))}
      </div>
      {failures &&
        !data.cases.some((c) => ["fail", "error"].includes(c.status)) && (
          <p className="muted">No hay fallos registrados.</p>
        )}
    </section>
  );
}
