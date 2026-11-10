import { useAuth } from "../components/AuthProvider";
import { useCallback, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  Clock3,
  FolderKanban,
  Globe2,
  Pencil,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useResource } from "../hooks/useResource";
import { projectsApi } from "../services/projects";
import { formatDate } from "../services/format";
import { ResourceError, ResourceLoading } from "../components/ResourceFeedback";
import { DeleteProjectDialog } from "../components/DeleteProjectDialog";
import { RunStartPanel } from "../components/RunStartPanel";
import { RunHistory } from "../components/RunHistory";
import { ProjectAnalytics } from "../components/ProjectAnalytics";

export function ProjectDetail() {
  const { role, canWrite } = useAuth();
  const { id = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const [deleting, setDeleting] = useState(false);
  const loader = useCallback(
    (signal: AbortSignal) => projectsApi.get(id, signal),
    [id],
  );
  const { state, reload } = useResource(loader);
  return (
    <>
      <Link className="back-link" to="/projects">
        <ArrowLeft size={14} />
        Todos los proyectos
      </Link>
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError
          message={state.message}
          onRetry={reload}
          notFound={state.code === 404 || state.code === 422}
        />
      ) : (
        <>
          <div className="page-heading detail-heading">
            <div>
              <p className="eyebrow">DETALLE DEL PROYECTO</p>
              <h1>
                {state.data.name}
                <span className="heading-dot">.</span>
              </h1>
              <p className="page-description">
                La información y los límites de tu aplicación.
              </p>
            </div>
            <div className="heading-actions">
              {canWrite && (
                <Link className="button-secondary" to={`/projects/${id}/edit`}>
                  <Pencil size={15} />
                  Editar
                </Link>
              )}
              {["owner", "admin"].includes(role) && (
                <button
                  className="button-danger"
                  onClick={() => setDeleting(true)}
                >
                  <Trash2 size={15} />
                  Eliminar
                </button>
              )}
            </div>
          </div>
          {typeof location.state?.notice === "string" && (
            <div className="inline-alert success-alert" role="status">
              <CheckCircle2 size={17} />
              {location.state.notice}
            </div>
          )}
          <div className="project-detail-grid">
            <section className="panel project-info-panel">
              <div className="panel-heading">
                <h2>
                  <FolderKanban size={17} />
                  Información general
                </h2>
              </div>
              <dl className="project-data">
                <div>
                  <dt>
                    <Globe2 size={14} />
                    URL base
                  </dt>
                  <dd className="project-detail-url">{state.data.base_url}</dd>
                </div>
                <div>
                  <dt>Descripción</dt>
                  <dd className="project-description-text">
                    {state.data.description || "Sin descripción."}
                  </dd>
                </div>
                <div>
                  <dt>
                    <Clock3 size={14} />
                    Creado
                  </dt>
                  <dd>{formatDate(state.data.created_at)}</dd>
                </div>
                <div>
                  <dt>
                    <Clock3 size={14} />
                    Última actualización
                  </dt>
                  <dd>{formatDate(state.data.updated_at)}</dd>
                </div>
                <div>
                  <dt>Identificador</dt>
                  <dd className="project-identifier">{state.data.id}</dd>
                </div>
              </dl>
            </section>
            <section className="panel project-limits">
              <div className="panel-heading">
                <div>
                  <h2>
                    <ShieldCheck size={17} />
                    Límites iniciales
                  </h2>
                  <p>Valores históricos del proyecto</p>
                </div>
              </div>
              <dl className="project-data">
                <div>
                  <dt>Páginas máximas</dt>
                  <dd>{state.data.max_pages}</dd>
                </div>
                <div>
                  <dt>Profundidad máxima</dt>
                  <dd>{state.data.max_depth}</dd>
                </div>
                <div>
                  <dt>Duración máxima</dt>
                  <dd>{state.data.max_duration_seconds} segundos</dd>
                </div>
              </dl>
              <div className="form-safety">
                <ShieldCheck size={18} />
                <p>
                  Los límites de cada ejecución se eligen en el formulario de
                  análisis. Estas referencias del proyecto se conservan.
                </p>
              </div>
            </section>
          </div>
          <RunStartPanel project={state.data} />
          <ProjectAnalytics key={state.data.id} projectId={state.data.id} />
          <RunHistory projectId={state.data.id} />
          {deleting && (
            <DeleteProjectDialog
              project={state.data}
              onClose={() => setDeleting(false)}
              onDeleted={() =>
                navigate("/projects", {
                  replace: true,
                  state: { notice: "Proyecto eliminado correctamente." },
                })
              }
            />
          )}
        </>
      )}
    </>
  );
}
