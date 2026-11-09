import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ArrowLeft, ArrowRight } from "lucide-react";
import { EmptyState } from "./EmptyState";
import { ResourceError, ResourceLoading } from "./ResourceFeedback";
import { usePollingResource } from "../hooks/usePollingResource";
import { activeRun, runsApi, runLabels } from "../services/runs";
import { formatDate } from "../services/format";
import type { RunList } from "../types/api";

const shouldPoll = (list: RunList) => list.items.some(activeRun);
export function RunHistory({ projectId }: { projectId?: string }) {
  const [offset, setOffset] = useState(0);
  const loader = useCallback(
    (signal: AbortSignal) => runsApi.list(projectId, offset, signal),
    [projectId, offset],
  );
  const { state, reload } = usePollingResource(loader, shouldPoll);
  if (state.status === "loading") return <ResourceLoading />;
  if (state.status === "error")
    return <ResourceError message={state.message} onRetry={reload} />;
  return (
    <section className="panel run-history">
      <div className="panel-heading">
        <div>
          <h2>
            Historial de análisis
            <span className="count-badge">{state.data.total}</span>
          </h2>
          <p>Resultados reales de las ejecuciones registradas</p>
        </div>
        <button className="button-secondary" onClick={reload}>
          Actualizar
        </button>
      </div>
      {state.data.items.length ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ANÁLISIS</th>
                <th>ESTADO</th>
                <th>PÁGINAS</th>
                <th>INCIDENCIAS</th>
                <th>FECHA</th>
              </tr>
            </thead>
            <tbody>
              {state.data.items.map((run) => (
                <tr key={run.id}>
                  <td>
                    <Link className="run-link" to={`/runs/${run.id}`}>
                      {run.id.slice(0, 8)}
                      <ArrowRight size={12} />
                    </Link>
                  </td>
                  <td>
                    <span
                      className={`status-pill ${run.status === "completed" ? "green" : run.status === "failed" ? "red" : "neutral"}`}
                    >
                      {runLabels[run.status]}
                    </span>
                  </td>
                  <td>{run.pages_scanned}</td>
                  <td>{run.issues_found}</td>
                  <td>{formatDate(run.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <EmptyState
          icon={Activity}
          title="Todavía no hay análisis"
          description="Inicia una ejecución autorizada desde un proyecto de demostración. Los resultados aparecerán aquí."
        />
      )}
      {state.data.total > 20 && (
        <div className="pagination run-pagination">
          <span>
            {offset + 1}–{offset + state.data.items.length} de{" "}
            {state.data.total}
          </span>
          <div>
            <button
              className="button-secondary"
              disabled={!offset}
              onClick={() => setOffset((value) => Math.max(0, value - 20))}
            >
              <ArrowLeft size={13} />
              Anterior
            </button>
            <button
              className="button-secondary"
              disabled={offset + 20 >= state.data.total}
              onClick={() => setOffset((value) => value + 20)}
            >
              Siguiente
              <ArrowRight size={13} />
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
