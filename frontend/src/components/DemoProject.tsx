import { useAuth } from "./AuthProvider";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FlaskConical, Plus } from "lucide-react";
import { useResource } from "../hooks/useResource";
import { runsApi } from "../services/runs";
import { projectsApi } from "../services/projects";

const load = (signal: AbortSignal) => runsApi.capabilities(signal);

export function DemoProject() {
  const { canWrite } = useAuth();
  const { state } = useResource(load);
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (state.status !== "ready") return null;
  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const project = await projectsApi.create({
        name: "Demostración BLACKBOX AI",
        description:
          "Aplicación integrada y controlada con fallos intencionados para verificar el motor. No se conecta a destinos externos.",
        base_url: state.data.demo_url,
      });
      navigate(`/projects/${project.id}`, {
        state: {
          notice:
            "Proyecto de demostración creado. Revisa y autoriza el análisis antes de iniciarlo.",
        },
      });
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo crear el proyecto.",
      );
      setBusy(false);
    }
  };
  return (
    <section className="panel demo-project-panel">
      <FlaskConical size={24} />
      <div>
        <h2>Prueba el motor con una demo controlada</h2>
        <p>
          {state.data.demo_enabled
            ? "Chromium analizará la aplicación integrada. El recorrido, los errores y las capturas se generarán al ejecutar el análisis."
            : "El motor está deshabilitado. Para probarlo en local, activa BLACKBOX_DEMO_TESTING_ENABLED y reinicia el backend."}
        </p>
        {error && (
          <p role="alert" className="field-error">
            {error}
          </p>
        )}
      </div>
      {state.data.demo_enabled && (
        <button
          className="button-secondary"
          onClick={create}
          disabled={busy || !canWrite}
        >
          <Plus size={14} />
          {busy ? "Creando…" : "Crear proyecto de demostración"}
        </button>
      )}
    </section>
  );
}
