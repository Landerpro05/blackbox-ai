import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowUpRight,
  CheckCheck,
  CircleDot,
  Clock3,
  Database,
  FolderKanban,
  Layers3,
  RefreshCw,
  ShieldAlert,
  Terminal,
  WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";
import { EmptyState } from "../components/EmptyState";
import { useOverview } from "../hooks/useOverview";
import type { RunStatus } from "../types/api";
import { API_BASE_URL } from "../services/api";

const number = new Intl.NumberFormat("es-ES");
const time = new Intl.DateTimeFormat("es-ES", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});
const dateTime = new Intl.DateTimeFormat("es-ES", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});
const runLabels: Record<RunStatus, string> = {
  queued: "En cola",
  running: "En ejecución",
  completed: "Completado",
  failed: "Fallido",
  cancelled: "Cancelado",
};
const ActivityChart = lazy(() => import("../components/ActivityChart"));

function Metric({
  label,
  value,
  detail,
  icon: Icon,
  color,
}: {
  label: string;
  value: number;
  detail: string;
  icon: LucideIcon;
  color: string;
}) {
  return (
    <section className="metric-card">
      <div className="metric-top">
        <span>{label}</span>
        <span className={`metric-icon ${color}`}>
          <Icon size={18} />
        </span>
      </div>
      <strong className="metric-value">{number.format(value)}</strong>
      <div className="metric-detail">
        <span className={`metric-dot ${color}`} />
        {detail}
      </div>
    </section>
  );
}

export function Dashboard() {
  const { state, refresh } = useOverview();
  const ready = state.status === "ready";
  const dashboard = ready ? state.dashboard : null;
  const hasTrend = dashboard?.trend.some(
    (point) => point.runs > 0 || point.issues > 0,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CENTRO DE CONTROL</p>
          <h1>
            Dashboard<span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            Una visión completa de la calidad de tus aplicaciones.
          </p>
        </div>
        <button
          className="button-secondary"
          onClick={refresh}
          disabled={state.status === "loading"}
        >
          <RefreshCw
            size={15}
            className={state.status === "loading" ? "spinning" : ""}
          />
          Actualizar
        </button>
      </div>
      <section
        className={`connection-strip ${state.status === "error" ? "connection-error" : ""}`}
        aria-live="polite"
      >
        <div>
          <span className={`connection-dot ${ready ? "connected" : ""}`} />
          <strong>
            {ready
              ? "Todos los sistemas conectados"
              : state.status === "loading"
                ? "Conectando con el backend…"
                : "Sin conexión con el backend"}
          </strong>
          <span className="strip-separator">/</span>
          <span>FastAPI + SQLite</span>
        </div>
        <span>
          {ready
            ? `Última consulta · ${time.format(new Date(state.dashboard.generated_at))}`
            : "Entorno local"}
        </span>
      </section>
      {state.status === "error" ? (
        <div className="panel error-panel" role="alert">
          <WifiOff size={30} />
          <h2>No hemos podido cargar los datos</h2>
          <p>{state.message}</p>
          <code>{API_BASE_URL}</code>
          <button className="button-primary" onClick={refresh}>
            <RefreshCw size={15} />
            Reintentar conexión
          </button>
          <p className="small-copy">
            Arranca el backend siguiendo el README y vuelve a intentarlo.
          </p>
        </div>
      ) : state.status === "loading" ? (
        <div
          className="loading-dashboard"
          aria-busy="true"
          aria-label="Cargando dashboard"
        >
          <div className="metrics-grid">
            {[1, 2, 3, 4].map((id) => (
              <div className="metric-card skeleton" key={id} />
            ))}
          </div>
          <div className="panel skeleton loading-panel" />
        </div>
      ) : (
        <>
          <div className="metrics-grid">
            <Metric
              label="Proyectos"
              value={state.dashboard.metrics.projects}
              detail="Aplicaciones en tu workspace"
              icon={FolderKanban}
              color="blue"
            />
            <Metric
              label="Análisis ejecutados"
              value={state.dashboard.metrics.runs}
              detail={`${state.dashboard.metrics.active_runs} en cola o en ejecución`}
              icon={Layers3}
              color="violet"
            />
            <Metric
              label="Errores detectados"
              value={state.dashboard.metrics.issues}
              detail="Hallazgos de todas las ejecuciones"
              icon={AlertCircle}
              color="amber"
            />
            <Metric
              label="Errores críticos"
              value={state.dashboard.metrics.critical_issues}
              detail="Hallazgos con severidad crítica"
              icon={ShieldAlert}
              color="rose"
            />
          </div>
          <div className="overview-grid">
            <section className="panel trend-panel">
              <div className="panel-heading">
                <div>
                  <h2>Actividad de análisis</h2>
                  <p>Ejecuciones y errores detectados por día</p>
                </div>
                <span className="period-chip">
                  <Clock3 size={12} />
                  14 días · UTC
                </span>
              </div>
              <div className="chart-legend">
                <span>
                  <i className="legend-dot blue-bg" />
                  Análisis
                </span>
                <span>
                  <i className="legend-dot amber-bg" />
                  Errores
                </span>
              </div>
              {hasTrend ? (
                <Suspense
                  fallback={
                    <div
                      className="chart skeleton"
                      aria-label="Cargando gráfico"
                    />
                  }
                >
                  <ActivityChart data={state.dashboard.trend} />
                </Suspense>
              ) : (
                <div className="empty-chart">
                  <div className="chart-grid-lines" />
                  <EmptyState
                    icon={Activity}
                    title="Tu actividad empieza aquí"
                    description="La evolución aparecerá cuando haya ejecuciones registradas. Todavía no hay datos en los últimos 14 días."
                  />
                </div>
              )}
              <div className="panel-bottom">
                <span>
                  <Database size={13} />
                  Datos reales de SQLite
                </span>
                <span>Actualización manual</span>
              </div>
            </section>
            <section className="panel system-panel">
              <div className="panel-heading">
                <div>
                  <h2>Estado del entorno</h2>
                  <p>La base de tu plataforma</p>
                </div>
                <Terminal size={18} className="muted" />
              </div>
              <div className="system-rows">
                <div>
                  <span className="system-icon">
                    <Activity size={17} />
                  </span>
                  <span>
                    <strong>API de backend</strong>
                    <small>FastAPI · v{state.health.version}</small>
                  </span>
                  <span className="status-pill green">Conectado</span>
                </div>
                <div>
                  <span className="system-icon">
                    <Database size={17} />
                  </span>
                  <span>
                    <strong>Base de datos</strong>
                    <small>SQLite · Persistencia local</small>
                  </span>
                  <span className="status-pill green">Conectada</span>
                </div>
                <div>
                  <span className="system-icon">
                    <CircleDot size={17} />
                  </span>
                  <span>
                    <strong>Motor de testing</strong>
                    <small>Disponible en la fase 3</small>
                  </span>
                  <span className="status-pill neutral">Pendiente</span>
                </div>
              </div>
              <div className="foundation-note">
                <CheckCheck size={17} />
                <div>
                  <strong>Fundación conectada</strong>
                  <p>
                    El dashboard consulta la API y la base de datos de este
                    workspace.
                  </p>
                </div>
              </div>
            </section>
          </div>
          <section className="panel history-panel">
            <div className="panel-heading">
              <div>
                <h2>
                  Ejecuciones recientes
                  <span className="count-badge">
                    {state.dashboard.metrics.runs}
                  </span>
                </h2>
                <p>Historial de análisis de tus aplicaciones</p>
              </div>
              <span className="subtle-label">Últimas 8 ejecuciones</span>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>PROYECTO</th>
                    <th>ESTADO</th>
                    <th>PÁGINAS</th>
                    <th>ERRORES</th>
                    <th>
                      FECHA <ArrowDown size={11} />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {state.dashboard.recent_runs.map((run) => (
                    <tr key={run.id}>
                      <td className="project-cell">
                        <span className="table-project-icon">
                          <FolderKanban size={16} />
                        </span>
                        {run.project_name}
                      </td>
                      <td>
                        <span
                          className={`status-pill ${run.status === "completed" ? "green" : run.status === "failed" ? "red" : "neutral"}`}
                        >
                          {runLabels[run.status]}
                        </span>
                      </td>
                      <td>{run.pages_visited}</td>
                      <td>{run.issue_count}</td>
                      <td>{dateTime.format(new Date(run.created_at))}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!state.dashboard.recent_runs.length && (
              <EmptyState
                icon={Layers3}
                title="Aún no hay ejecuciones"
                description="Tus análisis y sus resultados aparecerán aquí. El motor de testing se implementará en la fase 3."
              />
            )}
          </section>
          <section className="panel projects-panel">
            <div className="panel-heading">
              <div>
                <h2>
                  Tus proyectos
                  <span className="count-badge">
                    {state.dashboard.metrics.projects}
                  </span>
                </h2>
                <p>Aplicaciones que forman parte de tu workspace</p>
              </div>
              <Link className="button-secondary" to="/projects">
                Ver proyectos
                <ArrowUpRight size={13} />
              </Link>
            </div>
            {state.dashboard.projects.length ? (
              <div className="projects-grid">
                {state.dashboard.projects.map((project) => (
                  <article className="project-overview" key={project.id}>
                    <FolderKanban size={20} />
                    <h3>
                      <Link to={`/projects/${project.id}`}>{project.name}</Link>
                    </h3>
                    <p className="project-url">{project.base_url}</p>
                    <span>{project.run_count} análisis registrados</span>
                  </article>
                ))}
              </div>
            ) : (
              <div className="project-empty">
                <span className="empty-icon">
                  <FolderKanban size={22} strokeWidth={1.5} />
                </span>
                <div>
                  <h3>Un espacio para tus aplicaciones</h3>
                  <p>
                    Todavía no tienes proyectos. Registra tu primera aplicación
                    para organizar su información.
                  </p>
                </div>
                <Link className="button-secondary" to="/projects/new">
                  Crear proyecto
                </Link>
              </div>
            )}
          </section>
        </>
      )}
      <div className="scope-note">
        <ShieldAlert size={14} />
        <span>
          Analiza únicamente aplicaciones propias o autorizadas. En esta fase no
          se realizan peticiones a destinos externos.
        </span>
        <a
          href={`${API_BASE_URL.replace(/\/api\/v1$/, "")}/docs`}
          target="_blank"
          rel="noreferrer"
        >
          Explorar API
          <ArrowUpRight size={13} />
        </a>
      </div>
    </>
  );
}
