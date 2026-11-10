import { useAuth } from "../components/AuthProvider";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  Camera,
  Clock3,
  FileSearch,
  LoaderCircle,
  RefreshCw,
  Square,
} from "lucide-react";
import { usePollingResource } from "../hooks/usePollingResource";
import { activeRun, evidenceUrl, runsApi, runLabels } from "../services/runs";
import { formatDate } from "../services/format";
import { EmptyState } from "../components/EmptyState";
import { ReportPanel } from "../components/ReportPanel";
import { AIIntelligencePanel } from "../components/AIIntelligencePanel";
import { SuiteResults } from "../components/SuiteResults";
import { severityLabels } from "../services/reporting";
import { ResourceError, ResourceLoading } from "../components/ResourceFeedback";
import type { RunDetailData, TestIssue } from "../types/api";

const shouldPoll = (data: RunDetailData) => activeRun(data.run);

function RunResults({
  data,
  reload,
}: {
  data: RunDetailData;
  reload: () => void;
}) {
  const { canWrite } = useAuth();
  const [filter, setFilter] = useState("all");
  const [cancelling, setCancelling] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const run = data.run;
  const active = activeRun(run);
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [active]);
  useEffect(() => {
    if (!active) setCancelling(false);
  }, [active]);
  const cancel = async () => {
    setCancelling(true);
    setError("");
    try {
      await runsApi.cancel(run.id);
      reload();
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo solicitar la cancelación.",
      );
      setCancelling(false);
    }
  };
  const duration =
    active && run.started_at
      ? Math.max(run.duration_ms, now - Date.parse(run.started_at))
      : run.duration_ms;
  const issues =
    filter === "all"
      ? data.issues
      : data.issues.filter((issue) => issue.severity === filter);
  return (
    <>
      <Link className="back-link" to={`/projects/${run.project_id}`}>
        <ArrowLeft size={14} />
        Volver al proyecto
      </Link>
      <div className="page-heading detail-heading">
        <div>
          <p className="eyebrow">
            EJECUCIÓN {run.id.slice(0, 8).toUpperCase()}
          </p>
          <h1>
            {active ? "Análisis en ejecución" : "Resultados del análisis"}
            <span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            {run.environment_snapshot?.name || "Demostración controlada"} ·{" "}
            {formatDate(run.created_at)}
          </p>
        </div>
        <div className="heading-actions">
          <button className="button-secondary" onClick={reload}>
            <RefreshCw size={14} />
            Actualizar
          </button>
          {active && canWrite && (
            <button
              className="button-danger"
              onClick={cancel}
              disabled={cancelling || run.cancellation_requested}
            >
              <Square size={14} />
              {cancelling || run.cancellation_requested
                ? "Cancelando…"
                : "Cancelar análisis"}
            </button>
          )}
        </div>
      </div>
      {error && (
        <div className="inline-alert error-alert" role="alert">
          {error}
        </div>
      )}
      {run.error_message && (
        <div className="inline-alert error-alert" role="alert">
          <AlertCircle size={17} />
          {run.error_message}
        </div>
      )}
      <section className="panel run-progress" aria-live="polite">
        <div>
          <span
            className={`status-pill ${run.status === "completed" ? "green" : run.status === "failed" ? "red" : "neutral"}`}
          >
            {active && <LoaderCircle size={12} className="spinning" />}
            {runLabels[run.status]}
          </span>
          <span>
            {active
              ? "Consulta automática cada 1,5 s"
              : "Ejecución finalizada · Resultados conservados"}
          </span>
        </div>
        <label htmlFor="run-budget">
          {run.pages_scanned} de hasta {run.limits.max_pages} páginas del
          presupuesto
        </label>
        <progress
          id="run-budget"
          max={run.limits.max_pages}
          value={run.pages_scanned}
        />
      </section>
      <div className="metrics-grid run-metrics">
        <div className="metric-card">
          <Activity size={18} />
          <span>Páginas analizadas</span>
          <strong className="metric-value">{run.pages_scanned}</strong>
        </div>
        <div className="metric-card">
          <AlertCircle size={18} />
          <span>Incidencias encontradas</span>
          <strong className="metric-value">{run.issues_found}</strong>
        </div>
        <div className="metric-card">
          <Clock3 size={18} />
          <span>Duración</span>
          <strong className="metric-value">
            {(Math.max(0, duration) / 1000).toFixed(1)}
            <small> s</small>
          </strong>
        </div>
        <div className="metric-card">
          <FileSearch size={18} />
          <span>Solicitudes observadas</span>
          <strong className="metric-value">{run.request_count}</strong>
        </div>
      </div>
      {run.suite_id && <SuiteResults key={`suite-${run.id}`} runId={run.id} />}
      {!active && <ReportPanel key={run.id} runId={run.id} />}
      {!active && <AIIntelligencePanel key={`ai-${run.id}`} runId={run.id} />}
      <section className="panel run-issues">
        <div className="panel-heading">
          <div>
            <h2>
              Incidencias detectadas
              <span className="count-badge">{data.issues.length}</span>
            </h2>
            <p>Errores técnicos y decisiones de la política de seguridad</p>
          </div>
          <label className="severity-filter">
            Severidad
            <select
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="all">Todas</option>
              {Object.entries(severityLabels).map(([key, value]) => (
                <option key={key} value={key}>
                  {value}
                </option>
              ))}
            </select>
          </label>
        </div>
        {issues.length ? (
          <div className="issue-list">
            {issues.map((issue) => (
              <IssueCard key={issue.id} issue={issue} />
            ))}
          </div>
        ) : (
          <EmptyState
            icon={FileSearch}
            title={
              active
                ? "Recopilando incidencias"
                : "Sin incidencias en esta vista"
            }
            description={
              active
                ? "Los hallazgos aparecerán conforme se registren las páginas."
                : "No hay hallazgos que coincidan con el filtro o las páginas analizadas."
            }
          />
        )}
      </section>
      <section className="panel scanned-pages">
        <div className="panel-heading">
          <div>
            <h2>
              Páginas y evidencias
              <span className="count-badge">{data.pages.length}</span>
            </h2>
            <p>
              Capturas de viewport con los campos sensibles de la demo
              enmascarados
            </p>
          </div>
        </div>
        {data.pages.length ? (
          <div className="evidence-grid">
            {data.pages.map((page) => (
              <article className="evidence-card" key={page.id}>
                {page.screenshot_url ? (
                  <a
                    href={evidenceUrl(page.screenshot_url)}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <img
                      src={evidenceUrl(page.screenshot_url)}
                      alt={`Captura de ${page.url}`}
                      loading="lazy"
                    />
                  </a>
                ) : (
                  <div className="no-screenshot">
                    <Camera size={25} />
                    Sin captura disponible
                  </div>
                )}
                <div className="evidence-card-body">
                  <p>{page.url}</p>
                  <div>
                    <span
                      className={`status-pill ${page.status_code && page.status_code >= 400 ? "red" : "neutral"}`}
                    >
                      {page.status_code
                        ? `HTTP ${page.status_code}`
                        : "Fallo de navegación"}
                    </span>
                    <span>{page.load_time_ms} ms</span>
                    <span>Prof. {page.depth}</span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <EmptyState
            icon={Camera}
            title="Todavía no hay páginas registradas"
            description={
              active
                ? "El motor está preparando el navegador o esperando la primera navegación."
                : "La ejecución terminó antes de guardar una página."
            }
          />
        )}
      </section>
      <section className="panel run-technical">
        <details>
          <summary>Detalles técnicos de la ejecución</summary>
          <dl>
            <div>
              <dt>Identificador</dt>
              <dd>{run.id}</dd>
            </div>
            <div>
              <dt>Inicio</dt>
              <dd>
                {run.started_at ? formatDate(run.started_at) : "Pendiente"}
              </dd>
            </div>
            <div>
              <dt>Fin</dt>
              <dd>
                {run.finished_at ? formatDate(run.finished_at) : "En curso"}
              </dd>
            </div>
            <div>
              <dt>Límites aplicados</dt>
              <dd>{JSON.stringify(run.limits)}</dd>
            </div>
            <div>
              <dt>Modo de red</dt>
              <dd>Solo demo integrada. Destinos remotos deshabilitados.</dd>
            </div>
          </dl>
        </details>
      </section>
    </>
  );
}

function IssueCard({ issue }: { issue: TestIssue }) {
  return (
    <article className="issue-card">
      <div>
        <span className={`status-pill severity-${issue.severity}`}>
          {severityLabels[issue.severity]}
        </span>
        <h3>{issue.title}</h3>
        <span className="issue-kind">{issue.type}</span>
      </div>
      <p className="issue-url">{issue.url}</p>
      <details>
        <summary>Ver detalles técnicos</summary>
        <p className="issue-description">{issue.description}</p>
        <p>Detectado: {formatDate(issue.created_at)}</p>
      </details>
      {issue.evidence_url && (
        <a
          className="run-link"
          href={evidenceUrl(issue.evidence_url)}
          target="_blank"
          rel="noreferrer"
        >
          Ver evidencia
          <ArrowUpRight size={13} />
        </a>
      )}
    </article>
  );
}

export function RunDetail() {
  const { id = "" } = useParams();
  const loader = useCallback(
    (signal: AbortSignal) => runsApi.details(id, signal),
    [id],
  );
  const { state, reload } = usePollingResource(loader, shouldPoll);
  return state.status === "loading" ? (
    <ResourceLoading />
  ) : state.status === "error" ? (
    <ResourceError
      message={state.message}
      onRetry={reload}
      notFound={state.code === 404}
    />
  ) : (
    <RunResults data={state.data} reload={reload} />
  );
}
