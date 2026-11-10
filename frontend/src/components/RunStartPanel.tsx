import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { FlaskConical, LoaderCircle, Play } from "lucide-react";
import { useResource } from "../hooks/useResource";
import { runsApi } from "../services/runs";
import type { Project, RunLimits } from "../types/api";
import { useAuth } from "./AuthProvider";

const load = (signal: AbortSignal) => runsApi.capabilities(signal);
const labels: Record<keyof RunLimits, string> = {
  max_pages: "Páginas máximas",
  max_depth: "Profundidad",
  navigation_timeout_seconds: "Timeout de navegación (s)",
  timeout_seconds: "Timeout global (s)",
  max_requests: "Peticiones máximas",
};

export function RunStartPanel({ project }: { project: Project }) {
  const { canWrite } = useAuth();
  const { state, reload } = useResource(load);
  const navigate = useNavigate();
  const [limits, setLimits] = useState<RunLimits | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (state.status === "ready") setLimits(state.data.defaults);
  }, [state]);
  if (state.status === "loading")
    return (
      <div className="panel resource-loading" role="status">
        Consultando disponibilidad del motor…
      </div>
    );
  if (state.status === "error")
    return (
      <div className="inline-alert error-alert" role="alert">
        {state.message}
        <button className="button-secondary" onClick={reload}>
          Reintentar
        </button>
      </div>
    );
  const eligible =
    canWrite &&
    state.data.demo_enabled &&
    new URL(project.base_url).origin === new URL(state.data.demo_url).origin;
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!eligible || !consent || !limits || busy) return;
    setBusy(true);
    setError("");
    try {
      const run = await runsApi.start(project.id, limits);
      navigate(`/runs/${run.id}`);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo iniciar el análisis.",
      );
      setBusy(false);
    }
  };
  return (
    <form className="panel run-start-panel" onSubmit={submit} aria-busy={busy}>
      <div className="panel-heading">
        <div>
          <h2>
            <FlaskConical size={18} />
            Motor Playwright · Demostración controlada
          </h2>
          <p>Un navegador, un análisis activo y resultados persistentes.</p>
        </div>
        <span className="status-pill neutral">Internet deshabilitado</span>
      </div>
      <div className="run-start-body">
        <p className="run-mode-explanation">
          {!state.data.demo_enabled
            ? "Activa BLACKBOX_DEMO_TESTING_ENABLED=true en el servidor local y reinícialo para habilitar la demo."
            : !eligible
              ? `Este proyecto no pertenece a la demo integrada. El único origen autorizado es ${state.data.demo_url}. Puedes crear un proyecto de demostración desde Proyectos.`
              : "Se ejecutará Chromium sobre contenido integrado de la demo. No se visitarán otras aplicaciones locales ni sitios de Internet."}
        </p>
        {limits && (
          <fieldset className="run-limits-fields" disabled={!eligible || busy}>
            {(Object.keys(labels) as (keyof RunLimits)[]).map((key) => (
              <div className="form-field" key={key}>
                <label htmlFor={`run-${key}`}>{labels[key]}</label>
                <input
                  id={`run-${key}`}
                  type="number"
                  required
                  min={key === "max_depth" ? 0 : 1}
                  max={state.data.maximums[key]}
                  value={limits[key]}
                  onChange={(event) =>
                    setLimits(
                      (current) =>
                        current && {
                          ...current,
                          [key]: Number(event.target.value),
                        },
                    )
                  }
                />
              </div>
            ))}
          </fieldset>
        )}
        <label className="run-consent">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
            required
            disabled={!eligible || busy}
          />
          Autorizo analizar únicamente la demostración integrada de BLACKBOX AI.
        </label>
        {error && (
          <div className="inline-alert error-alert" role="alert">
            {error}
          </div>
        )}
        <button
          className="button-primary"
          type="submit"
          disabled={!eligible || !consent || busy}
        >
          {busy ? (
            <LoaderCircle size={15} className="spinning" />
          ) : (
            <Play size={15} />
          )}
          {busy ? "Iniciando…" : "Iniciar análisis"}
        </button>
      </div>
    </form>
  );
}
