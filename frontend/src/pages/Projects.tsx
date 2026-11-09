import { useCallback, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  FolderKanban,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { projectsApi } from "../services/projects";
import { formatDate } from "../services/format";
import { useResource } from "../hooks/useResource";
import type { Project } from "../types/api";
import { EmptyState } from "../components/EmptyState";
import { ResourceError, ResourceLoading } from "../components/ResourceFeedback";
import { DeleteProjectDialog } from "../components/DeleteProjectDialog";

export function Projects() {
  const location = useLocation();
  const [notice, setNotice] = useState<string>(
    typeof location.state?.notice === "string" ? location.state.notice : "",
  );
  const [offset, setOffset] = useState(0);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const loader = useCallback(
    (signal: AbortSignal) => projectsApi.list(offset, signal),
    [offset],
  );
  const { state, reload } = useResource(loader);
  const deleted = () => {
    setDeleting(null);
    setNotice("Proyecto eliminado correctamente.");
    if (state.status === "ready" && offset > 0 && state.data.items.length === 1)
      setOffset((value) => Math.max(0, value - 12));
    else reload();
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">TUS APLICACIONES</p>
          <h1>
            Proyectos<span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            Organiza las aplicaciones que quieres poner a prueba.
          </p>
        </div>
        <Link className="button-primary" to="/projects/new">
          <Plus size={16} />
          Nuevo proyecto
        </Link>
      </div>
      {notice && (
        <div className="inline-alert success-alert" role="status">
          <CheckCircle2 size={17} />
          {notice}
          <button
            className="notice-dismiss"
            onClick={() => setNotice("")}
            aria-label="Cerrar mensaje"
          >
            ×
          </button>
        </div>
      )}
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : (
        <>
          <div className="project-list-toolbar">
            <span>
              {state.data.total}{" "}
              {state.data.total === 1
                ? "proyecto registrado"
                : "proyectos registrados"}
            </span>
            <button className="button-secondary" onClick={reload}>
              <RefreshCw size={14} />
              Actualizar
            </button>
          </div>
          {state.data.total === 0 ? (
            <section className="panel projects-empty-panel">
              <EmptyState
                icon={FolderKanban}
                title="Tu primer proyecto empieza aquí"
                description="Registra el nombre y la URL de tu aplicación. Guardarla no inicia pruebas ni accede a su contenido."
              />
              <Link className="button-primary" to="/projects/new">
                <Plus size={16} />
                Crear primer proyecto
              </Link>
            </section>
          ) : state.data.items.length === 0 ? (
            <section className="panel projects-empty-panel">
              <p>Esta página ya no contiene proyectos.</p>
              <button className="button-secondary" onClick={() => setOffset(0)}>
                Volver a la primera página
              </button>
            </section>
          ) : (
            <div className="project-cards">
              {state.data.items.map((project) => (
                <article className="panel project-card" key={project.id}>
                  <div className="project-card-top">
                    <span className="empty-icon">
                      <FolderKanban size={22} />
                    </span>
                    <div className="project-card-actions">
                      <Link
                        className="icon-button"
                        to={`/projects/${project.id}/edit`}
                        aria-label={`Editar ${project.name}`}
                      >
                        <Pencil size={16} />
                      </Link>
                      <button
                        className="icon-button delete-action"
                        onClick={() => setDeleting(project)}
                        aria-label={`Eliminar ${project.name}`}
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                  <Link
                    className="project-card-title"
                    to={`/projects/${project.id}`}
                  >
                    {project.name}
                    <ArrowUpRight size={16} />
                  </Link>
                  <p className="project-base-url">{project.base_url}</p>
                  <p className="project-card-description">
                    {project.description || "Sin descripción."}
                  </p>
                  <div className="project-card-footer">
                    <span>Creado {formatDate(project.created_at)}</span>
                    <Link to={`/projects/${project.id}`}>
                      Ver detalles
                      <ArrowRight size={13} />
                    </Link>
                  </div>
                </article>
              ))}
            </div>
          )}
          {state.data.total > 0 && (
            <nav className="pagination" aria-label="Páginas de proyectos">
              <span>
                {state.data.items.length
                  ? `${offset + 1}–${offset + state.data.items.length}`
                  : "0"}{" "}
                de {state.data.total}
              </span>
              <div>
                <button
                  className="button-secondary"
                  disabled={offset === 0}
                  onClick={() => setOffset((value) => Math.max(0, value - 12))}
                >
                  <ArrowLeft size={14} />
                  Anterior
                </button>
                <button
                  className="button-secondary"
                  disabled={offset + state.data.limit >= state.data.total}
                  onClick={() => setOffset((value) => value + 12)}
                >
                  Siguiente
                  <ArrowRight size={14} />
                </button>
              </div>
            </nav>
          )}
        </>
      )}
      <p className="project-scope-note">
        Workspace local · Los proyectos registrados no otorgan autorización
        automática para realizar pruebas.
      </p>
      {deleting && (
        <DeleteProjectDialog
          project={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={deleted}
        />
      )}
    </>
  );
}
