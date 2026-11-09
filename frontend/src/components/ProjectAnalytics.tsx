import { lazy, Suspense, useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { BarChart3 } from "lucide-react";
import { useResource } from "../hooks/useResource";
import {
  reportingApi,
  classificationLabels,
  severityLabels,
} from "../services/reporting";
import { ResourceError, ResourceLoading } from "./ResourceFeedback";
import { EmptyState } from "./EmptyState";

const AnalyticsChart = lazy(() => import("./AnalyticsChart"));

export function ProjectAnalytics({ projectId }: { projectId: string }) {
  const [offset, setOffset] = useState(0);
  const loader = useCallback(
    (signal: AbortSignal) => reportingApi.analytics(projectId, offset, signal),
    [projectId, offset],
  );
  const { state, reload } = useResource(loader);
  return (
    <section className="panel reporting-panel project-analytics">
      <div className="panel-heading">
        <div>
          <h2>
            <BarChart3 size={18} /> Evolución de calidad
          </h2>
          <p>
            Histórico real del proyecto · Incidencias acumuladas, no errores
            únicos
          </p>
        </div>
        <button className="button-secondary" onClick={reload}>
          Actualizar métricas
        </button>
      </div>
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : state.data.total_runs === 0 ? (
        <EmptyState
          icon={BarChart3}
          title="Tu histórico empieza con el primer análisis"
          description="Cuando finalice una ejecución podrás descargar sus informes y comparar resultados."
        />
      ) : (
        <>
          <dl className="report-facts">
            <div>
              <dt>Ejecuciones</dt>
              <dd>{state.data.total_runs}</dd>
            </div>
            <div>
              <dt>Incidencias acumuladas</dt>
              <dd>{state.data.total_issues}</dd>
            </div>
            <div>
              <dt>Navegación media</dt>
              <dd>
                {state.data.average_navigation_ms === null
                  ? "Sin datos"
                  : `${state.data.average_navigation_ms} ms`}
              </dd>
            </div>
          </dl>
          <p className="chart-legend">
            <span>● Incidencias</span>
            <span>● Navegación (ms)</span>
          </p>
          <Suspense fallback={<ResourceLoading />}>
            <AnalyticsChart items={state.data.items} />
          </Suspense>
          <div className="analytics-breakdowns">
            <div>
              <h3>Por severidad</h3>
              {Object.entries(state.data.by_severity).map(([key, value]) => (
                <div className="distribution-row" key={key}>
                  <span>
                    {severityLabels[key as keyof typeof severityLabels]}
                  </span>
                  <meter
                    value={value}
                    max={Math.max(1, state.data.total_issues)}
                  />
                  <strong>{value}</strong>
                </div>
              ))}
            </div>
            <div>
              <h3>Por tipo</h3>
              {state.data.by_type.map((item) => (
                <div className="distribution-row" key={item.type}>
                  <span>{item.type}</span>
                  <meter
                    value={item.count}
                    max={Math.max(1, state.data.total_issues)}
                  />
                  <strong>{item.count}</strong>
                </div>
              ))}
              {!state.data.by_type.length && (
                <p className="report-note">Sin incidencias registradas.</p>
              )}
              {state.data.types_truncated && <p>Se muestran hasta 50 tipos.</p>}
            </div>
          </div>
          <h3>Última comparación disponible</h3>
          {state.data.regression ? (
            <>
              <div className="severity-summary">
                {Object.entries(state.data.regression.counts).map(
                  ([key, value]) => (
                    <div key={key}>
                      <span>
                        {
                          classificationLabels[
                            key as keyof typeof classificationLabels
                          ]
                        }
                      </span>
                      <strong>{value}</strong>
                    </div>
                  ),
                )}
              </div>
              <p className="report-note">
                Base {state.data.regression.base_run_id.slice(0, 8)} → Destino{" "}
                {state.data.regression.target_run_id.slice(0, 8)}.{" "}
                {state.data.regression.partial
                  ? "Cobertura parcial: las ausencias quedan sin confirmar."
                  : "Resoluciones heurísticas limitadas a páginas revisitadas."}
              </p>
            </>
          ) : (
            <p className="report-note">
              Se necesitan dos ejecuciones finalizadas para comparar.
            </p>
          )}
          <Link className="run-link" to={`/reports?project=${projectId}`}>
            Comparar ejecuciones del proyecto →
          </Link>
          <div className="analytics-recent">
            <h3>Ejecuciones de esta página · Acceso al informe</h3>
            {state.data.items.map((run) => (
              <Link className="run-link" to={`/runs/${run.id}`} key={run.id}>
                {run.id.slice(0, 8)} · {run.status} · {run.issues} incidencias →
              </Link>
            ))}
          </div>
          <div className="pagination">
            <span>
              {offset + 1}–
              {Math.min(
                offset + state.data.items.length,
                state.data.total_runs,
              )}{" "}
              de {state.data.total_runs}
            </span>
            <div>
              <button
                className="button-secondary"
                disabled={offset === 0}
                onClick={() => setOffset((value) => Math.max(0, value - 20))}
              >
                Más recientes
              </button>
              <button
                className="button-secondary"
                disabled={offset + 20 >= state.data.total_runs}
                onClick={() => setOffset((value) => value + 20)}
              >
                Más antiguas
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
