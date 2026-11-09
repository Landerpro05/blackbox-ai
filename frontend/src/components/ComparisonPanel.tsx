import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { GitCompareArrows } from "lucide-react";
import { useResource } from "../hooks/useResource";
import { projectsApi } from "../services/projects";
import { activeRun, runsApi, runLabels, evidenceUrl } from "../services/runs";
import {
  reportingApi,
  classificationLabels,
  severityLabels,
} from "../services/reporting";
import { formatDate } from "../services/format";
import type { Classification, Comparison } from "../types/reporting";
import { ResourceError, ResourceLoading } from "./ResourceFeedback";

function RunComparison({ projectId }: { projectId: string }) {
  const [offset, setOffset] = useState(0);
  const [base, setBase] = useState("");
  const [target, setTarget] = useState("");
  const [result, setResult] = useState<Comparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<Classification | "all">("all");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const loader = useCallback(
    (signal: AbortSignal) => runsApi.list(projectId, offset, signal),
    [projectId, offset],
  );
  const { state, reload } = useResource(loader);
  useEffect(() => {
    if (state.status !== "ready") return;
    const finished = state.data.items.filter((run) => !activeRun(run));
    if (!target && finished[0]) setTarget(finished[0].id);
    if (!base && finished[1]) setBase(finished[1].id);
  }, [state, base, target]);
  const compare = async () => {
    controller.current = new AbortController();
    setBusy(true);
    setError("");
    setResult(null);
    try {
      setResult(
        await reportingApi.compare(
          projectId,
          base,
          target,
          controller.current.signal,
        ),
      );
    } catch (caught) {
      if (!controller.current.signal.aborted)
        setError(
          caught instanceof Error ? caught.message : "No se pudo comparar.",
        );
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : (
        <>
          <div className="comparison-fields">
            {(["base", "target"] as const).map((which) => {
              const value = which === "base" ? base : target;
              return (
                <label key={which}>
                  {which === "base"
                    ? "Ejecución base (anterior)"
                    : "Ejecución destino (reciente)"}
                  <select
                    disabled={busy}
                    value={value}
                    onChange={(event) => {
                      (which === "base" ? setBase : setTarget)(
                        event.target.value,
                      );
                      setResult(null);
                      setError("");
                    }}
                  >
                    <option value="">Selecciona una ejecución</option>
                    {value &&
                      !state.data.items.some((run) => run.id === value) && (
                        <option value={value}>
                          {value.slice(0, 8)} · Seleccionada en otra página
                        </option>
                      )}
                    {state.data.items
                      .filter((run) => !activeRun(run))
                      .map((run) => (
                        <option value={run.id} key={run.id}>
                          {run.id.slice(0, 8)} · {formatDate(run.created_at)} ·{" "}
                          {runLabels[run.status]}
                        </option>
                      ))}
                  </select>
                </label>
              );
            })}
          </div>
          <div className="comparison-actions">
            <button
              className="button-primary"
              disabled={busy || !base || !target || base === target}
              onClick={() => void compare()}
            >
              <GitCompareArrows size={15} />
              {busy ? "Comparando…" : "Comparar ejecuciones"}
            </button>
            <button
              className="button-secondary"
              disabled={busy}
              onClick={reload}
            >
              Actualizar historial
            </button>
          </div>
          <p className="report-note">
            Elige una base anterior al destino. Las ejecuciones en curso no se
            pueden comparar.
          </p>
          {!state.data.items.length && (
            <p>
              No hay ejecuciones en esta página. Inicia un análisis desde el
              proyecto.
            </p>
          )}
          {state.data.total > 20 && (
            <div className="pagination">
              <span>
                Ejecuciones {offset + 1}–{offset + state.data.items.length} de{" "}
                {state.data.total}
              </span>
              <div>
                <button
                  className="button-secondary"
                  disabled={busy || !offset}
                  onClick={() => setOffset((value) => value - 20)}
                >
                  Más recientes
                </button>
                <button
                  className="button-secondary"
                  disabled={busy || offset + 20 >= state.data.total}
                  onClick={() => setOffset((value) => value + 20)}
                >
                  Más antiguas
                </button>
              </div>
            </div>
          )}
        </>
      )}
      {error && (
        <p className="inline-alert error-alert" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="comparison-results" aria-live="polite">
          <h3>Resultado de la comparación</h3>
          <div className="severity-summary">
            {Object.entries(result.counts).map(([key, value]) => (
              <div key={key}>
                <span>
                  {classificationLabels[key as Classification]}{" "}
                  <small>{key}</small>
                </span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <p className="report-note">{result.heuristic}</p>
          {result.warnings.map((warning) => (
            <p className="report-note" key={warning}>
              {warning}
            </p>
          ))}
          {Object.values(result.omitted).some(
            (value) => value.issues || value.pages,
          ) && (
            <p role="status">
              Comparación truncada por los límites de detalles. Las ausencias no
              se clasifican como resueltas.
            </p>
          )}
          <label className="severity-filter">
            Clasificación
            <select
              value={filter}
              aria-label="Clasificación"
              onChange={(event) =>
                setFilter(event.target.value as Classification | "all")
              }
            >
              <option value="all">Todas</option>
              {Object.entries(classificationLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label} ({key})
                </option>
              ))}
            </select>
          </label>
          <div className="issue-list">
            {result.items
              .filter(
                (item) => filter === "all" || item.classification === filter,
              )
              .map((item) => {
                const runId =
                  item.classification === "RESOLVED" ||
                  item.classification === "UNCONFIRMED"
                    ? result.base_run_id
                    : result.target_run_id;
                return (
                  <article
                    className="issue-card comparison-issue"
                    key={item.fingerprint}
                  >
                    <div>
                      <span
                        className={`status-pill ${item.classification === "NEW" ? "red" : item.classification === "RESOLVED" ? "green" : "neutral"}`}
                      >
                        {item.classification}
                      </span>
                      <h3>{item.issue.title}</h3>
                      <span
                        className={`status-pill severity-${item.issue.severity}`}
                      >
                        {severityLabels[item.issue.severity]}
                      </span>
                    </div>
                    <p className="issue-url">{item.issue.url}</p>
                    <p className="issue-description">
                      {item.issue.description}
                    </p>
                    <div>
                      <Link className="run-link" to={`/runs/${runId}`}>
                        Ver informe →
                      </Link>
                      {item.issue.evidence_page_id && (
                        <a
                          className="run-link"
                          href={evidenceUrl(
                            `/runs/${runId}/pages/${item.issue.evidence_page_id}/screenshot`,
                          )}
                          target="_blank"
                          rel="noreferrer"
                        >
                          Ver evidencia →
                        </a>
                      )}
                    </div>
                  </article>
                );
              })}
            {!result.items.some(
              (item) => filter === "all" || item.classification === filter,
            ) && (
              <p className="report-note">
                Sin incidencias en esta clasificación.
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export function ComparisonPanel() {
  const [params, setParams] = useSearchParams();
  const project = params.get("project") || "";
  const [offset, setOffset] = useState(0);
  const loader = useCallback(
    (signal: AbortSignal) => projectsApi.list(offset, signal),
    [offset],
  );
  const { state, reload } = useResource(loader);
  return (
    <section className="panel reporting-panel">
      <div className="panel-heading">
        <div>
          <h2>
            <GitCompareArrows size={18} /> Comparación de ejecuciones
          </h2>
          <p>
            Dos ejecuciones del mismo proyecto · Sin alterar resultados
            históricos
          </p>
        </div>
      </div>
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : (
        <>
          <label className="project-comparison-picker">
            Proyecto para comparar
            <select
              value={project}
              onChange={(event) =>
                setParams(
                  event.target.value ? { project: event.target.value } : {},
                )
              }
            >
              <option value="">Selecciona un proyecto</option>
              {project &&
                !state.data.items.some((item) => item.id === project) && (
                  <option value={project}>
                    Proyecto {project.slice(0, 8)}
                  </option>
                )}
              {state.data.items.map((item) => (
                <option value={item.id} key={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          {!state.data.total && (
            <p className="report-note">
              Crea un proyecto y ejecuta dos análisis para empezar a comparar.
            </p>
          )}
          {state.data.total > 12 && (
            <div className="pagination">
              <span>
                Proyectos {offset + 1}–{offset + state.data.items.length} de{" "}
                {state.data.total}
              </span>
              <div>
                <button
                  className="button-secondary"
                  disabled={!offset}
                  onClick={() => setOffset((value) => value - 12)}
                >
                  Anteriores
                </button>
                <button
                  className="button-secondary"
                  disabled={offset + 12 >= state.data.total}
                  onClick={() => setOffset((value) => value + 12)}
                >
                  Siguientes
                </button>
              </div>
            </div>
          )}
        </>
      )}
      {project && <RunComparison key={project} projectId={project} />}
    </section>
  );
}
