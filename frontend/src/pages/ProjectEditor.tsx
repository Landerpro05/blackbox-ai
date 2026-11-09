import { useCallback } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import { ProjectForm } from "../components/ProjectForm";
import { ResourceError, ResourceLoading } from "../components/ResourceFeedback";
import { useResource } from "../hooks/useResource";
import { projectsApi } from "../services/projects";
import type { Project, ProjectInput } from "../types/api";

function EditorHeading({ editing }: { editing: boolean }) {
  return (
    <>
      <Link className="back-link" to="/projects">
        <ArrowLeft size={14} />
        Todos los proyectos
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">GESTIÓN DE PROYECTOS</p>
          <h1>
            {editing ? "Editar proyecto" : "Nuevo proyecto"}
            <span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            {editing
              ? "Actualiza la información de tu aplicación."
              : "Define el punto de partida de tu próxima revisión."}
          </p>
        </div>
      </div>
    </>
  );
}

export function NewProject() {
  const navigate = useNavigate();
  const save = async (data: ProjectInput) => {
    const project = await projectsApi.create(data);
    navigate(`/projects/${project.id}`, {
      replace: true,
      state: { notice: "Proyecto creado correctamente." },
    });
  };
  return (
    <>
      <EditorHeading editing={false} />
      <ProjectForm onSave={save} cancelTo="/projects" />
    </>
  );
}

function EditForm({ project }: { project: Project }) {
  const navigate = useNavigate();
  const save = async (data: ProjectInput) => {
    const changes: Partial<ProjectInput> = {};
    for (const field of ["name", "description", "base_url"] as const) {
      if (data[field] !== project[field]) changes[field] = data[field];
    }
    if (Object.keys(changes).length > 0)
      await projectsApi.update(project.id, changes);
    navigate(`/projects/${project.id}`, {
      replace: true,
      state: {
        notice: Object.keys(changes).length
          ? "Cambios guardados correctamente."
          : "No había cambios que guardar.",
      },
    });
  };
  return (
    <ProjectForm
      initial={project}
      onSave={save}
      cancelTo={`/projects/${project.id}`}
      editing
    />
  );
}

export function EditProject() {
  const { id = "" } = useParams();
  const loader = useCallback(
    (signal: AbortSignal) => projectsApi.get(id, signal),
    [id],
  );
  const { state, reload } = useResource(loader);
  return (
    <>
      <EditorHeading editing />
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError
          message={state.message}
          onRetry={reload}
          notFound={state.code === 404 || state.code === 422}
        />
      ) : (
        <EditForm key={state.data.id} project={state.data} />
      )}
    </>
  );
}
