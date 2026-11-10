import { AlertCircle, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";

export function ResourceLoading({
  label = "Cargando proyectos…",
}: {
  label?: string;
}) {
  return (
    <div className="panel resource-loading" role="status">
      <RefreshCw size={20} className="spinning" />
      {label}
    </div>
  );
}

export function ResourceError({
  message,
  onRetry,
  notFound = false,
}: {
  message: string;
  onRetry: () => void;
  notFound?: boolean;
}) {
  return (
    <div className="panel error-panel" role="alert">
      <AlertCircle size={28} />
      <h2>
        {notFound
          ? "Proyecto no encontrado"
          : "No se pudieron cargar los datos"}
      </h2>
      <p>
        {notFound ? "El proyecto no existe o ya no está disponible." : message}
      </p>
      {notFound ? (
        <Link className="button-secondary" to="/projects">
          Volver a proyectos
        </Link>
      ) : (
        <button className="button-secondary" onClick={onRetry}>
          <RefreshCw size={15} />
          Reintentar
        </button>
      )}
    </div>
  );
}
