import { useEffect, useRef, useState } from "react";
import { AlertTriangle, LoaderCircle, Trash2 } from "lucide-react";
import type { Project } from "../types/api";
import { projectsApi } from "../services/projects";
import { ApiError } from "../services/api";

export function DeleteProjectDialog({
  project,
  onClose,
  onDeleted,
}: {
  project: Project;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    cancelRef.current?.focus();
    return () => dialog?.close();
  }, []);
  const remove = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await projectsApi.delete(project.id);
      onDeleted();
    } catch (caught) {
      // Another window may have deleted it already; reconcile with server state.
      if (caught instanceof ApiError && caught.status === 404) {
        onDeleted();
        return;
      }
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo eliminar el proyecto.",
      );
      setBusy(false);
    }
  };
  return (
    <dialog
      ref={ref}
      className="delete-dialog"
      aria-labelledby="delete-title"
      aria-describedby="delete-description"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <span className="delete-symbol">
        <AlertTriangle size={25} />
      </span>
      <h2 id="delete-title">¿Eliminar este proyecto?</h2>
      <p id="delete-description">
        Eliminarás <strong>{project.name}</strong> y todas sus ejecuciones y
        errores asociados. Esta acción no se puede deshacer.
      </p>
      {error && (
        <div className="inline-alert error-alert" role="alert">
          {error}
        </div>
      )}
      <div className="dialog-actions">
        <button
          ref={cancelRef}
          className="button-secondary"
          onClick={onClose}
          disabled={busy}
        >
          Cancelar
        </button>
        <button className="button-danger" onClick={remove} disabled={busy}>
          {busy ? (
            <LoaderCircle size={15} className="spinning" />
          ) : (
            <Trash2 size={15} />
          )}
          {busy ? "Eliminando…" : "Eliminar proyecto"}
        </button>
      </div>
    </dialog>
  );
}
