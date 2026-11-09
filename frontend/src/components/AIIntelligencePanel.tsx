import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { BrainCircuit, LoaderCircle } from "lucide-react";
import { useResource } from "../hooks/useResource";
import { usePollingResource } from "../hooks/usePollingResource";
import { activeAI, intelligenceApi } from "../services/intelligence";
import type {
  AICapabilities,
  AIAnalysis,
  AIAnalysisList,
} from "../types/intelligence";
import { ResourceError, ResourceLoading } from "./ResourceFeedback";
import { AIAnalysisResult } from "./AIAnalysisResult";

export const aiStatusLabels = {
  pending: "Pendiente",
  running: "Interpretando",
  completed: "Completado",
  failed: "Fallido",
  cancelled: "Cancelado",
};
const pollHistory = (list: AIAnalysisList) => list.items.some(activeAI);

function AIConfirmation({
  runId,
  capabilities,
  onClose,
  onCreated,
}: {
  runId: string;
  capabilities: AICapabilities;
  onClose: () => void;
  onCreated: (analysis: AIAnalysis) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [mode, setMode] = useState<"rules" | "llm">("rules");
  const [consent, setConsent] = useState(false);
  const [maximum, setMaximum] = useState(5);
  const [history, setHistory] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  const create = async () => {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      onCreated(
        await intelligenceApi.create(runId, {
          mode,
          authorize_external: mode === "llm" && consent,
          max_findings: maximum,
          include_history: history,
          consent_provider: mode === "llm" ? capabilities.provider : null,
          consent_model: mode === "llm" ? capabilities.model : null,
        }),
      );
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo crear el análisis.",
      );
      setBusy(false);
    }
  };
  return (
    <dialog
      ref={ref}
      className="delete-dialog ai-dialog"
      aria-labelledby="ai-confirm-title"
      onCancel={(event) => {
        if (busy) event.preventDefault();
        else onClose();
      }}
    >
      <h2 id="ai-confirm-title">Analizar incidencias</h2>
      <p>
        Revisa el modo antes de iniciar. El resultado será una interpretación;
        no aplicará correcciones ni ejecutará código.
      </p>
      <label>
        Modo de análisis
        <select
          aria-label="Modo de análisis"
          value={mode}
          disabled={busy}
          onChange={(event) => {
            setMode(event.target.value as "rules" | "llm");
            setConsent(false);
          }}
        >
          <option value="rules">Análisis basado en reglas · Local</option>
          <option value="llm" disabled={!capabilities.llm_enabled}>
            Modelo LLM · Proveedor externo
          </option>
        </select>
      </label>
      {mode === "rules" ? (
        <p className="form-safety">
          Diagnóstico determinista local. No utiliza un modelo generativo ni
          envía datos a una API externa.
        </p>
      ) : (
        <>
          <p className="inline-alert">
            Proveedor: <strong>{capabilities.provider}</strong> · Modelo:{" "}
            <strong>{capabilities.model}</strong>. Recibirá texto redactado de
            incidencias, URLs, páginas, tiempos y, si lo eliges, una comparación
            histórica. No se enviarán capturas. Su tratamiento de datos depende
            del proveedor configurado.
          </p>
          <p className="report-note">
            Hasta {capabilities.max_context_bytes} bytes de evidencias y{" "}
            {capabilities.max_output_tokens} tokens de salida por intento. Hasta{" "}
            {capabilities.max_attempts} intentos por solicitud.{" "}
            {capabilities.prices_configured
              ? "El backend reserva el coste estimado usando las tarifas configuradas."
              : "No hay tarifas configuradas: el coste monetario no puede estimarse."}{" "}
            Límite diario: {capabilities.daily_call_limit} solicitudes y{" "}
            {capabilities.daily_token_limit} tokens reservados.
            {capabilities.daily_budget_usd !== null &&
              ` Presupuesto: ${capabilities.daily_budget_usd} USD.`}
          </p>
          <label className="evidence-option">
            <input
              type="checkbox"
              checked={consent}
              disabled={busy}
              onChange={(event) => setConsent(event.target.checked)}
            />{" "}
            Autorizo enviar estas evidencias redactadas al proveedor y modelo
            indicados, con el coste que pueda generar.
          </label>
        </>
      )}
      {!capabilities.llm_enabled && (
        <p className="report-note">
          LLM externo sin configurar. El análisis basado en reglas está
          disponible sin clave.
        </p>
      )}
      <label>
        Máximo de hipótesis
        <input
          aria-label="Máximo de hipótesis"
          type="number"
          min={1}
          max={capabilities.max_findings}
          value={maximum}
          disabled={busy}
          onChange={(event) => setMaximum(Number(event.target.value))}
        />
      </label>
      <label className="evidence-option">
        <input
          type="checkbox"
          checked={history}
          disabled={busy}
          onChange={(event) => setHistory(event.target.checked)}
        />{" "}
        Incluir comparación con la ejecución anterior, si existe.
      </label>
      {error && (
        <p className="inline-alert error-alert" role="alert">
          {error}
        </p>
      )}
      <div className="dialog-actions">
        <button className="button-secondary" disabled={busy} onClick={onClose}>
          Cancelar
        </button>
        <button
          className="button-primary"
          disabled={
            busy ||
            !Number.isInteger(maximum) ||
            maximum < 1 ||
            maximum > capabilities.max_findings ||
            (mode === "llm" && !consent)
          }
          onClick={() => void create()}
        >
          {busy && <LoaderCircle className="spinning" size={14} />}Iniciar
          interpretación
        </button>
      </div>
    </dialog>
  );
}

export function AIIntelligencePanel({ runId }: { runId: string }) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const capabilitiesLoader = useCallback(
    (signal: AbortSignal) => intelligenceApi.capabilities(signal),
    [],
  );
  const capabilities = useResource(capabilitiesLoader);
  const loader = useCallback(
    (signal: AbortSignal) => intelligenceApi.list(runId, offset, signal),
    [runId, offset],
  );
  const { state, reload } = usePollingResource(loader, pollHistory);
  const [error, setError] = useState("");
  const [cancelling, setCancelling] = useState(false);
  const cancel = async (id: string) => {
    setCancelling(true);
    setError("");
    try {
      await intelligenceApi.cancel(id);
      reload();
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "No se pudo cancelar.",
      );
    } finally {
      setCancelling(false);
    }
  };
  const current =
    state.status === "ready"
      ? state.data.items.find((item) => item.id === selected) ||
        state.data.items[0]
      : null;
  return (
    <section
      className="panel reporting-panel ai-panel"
      aria-label="AI Intelligence"
    >
      <div className="panel-heading">
        <div>
          <h2>
            <BrainCircuit size={18} /> AI Intelligence
          </h2>
          <p>
            Hechos, hipótesis y propuestas de tests · Sin cambios automáticos
          </p>
        </div>
        <button
          className="button-primary"
          disabled={
            capabilities.state.status !== "ready" ||
            Boolean(current && activeAI(current))
          }
          onClick={() => setOpen(true)}
        >
          <BrainCircuit size={15} />
          Analizar con IA
        </button>
      </div>
      {capabilities.state.status === "error" && (
        <ResourceError
          message={capabilities.state.message}
          onRetry={capabilities.reload}
        />
      )}
      {state.status === "loading" ? (
        <ResourceLoading />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : !state.data.items.length ? (
        <p className="report-note">
          Todavía no hay interpretaciones. Puedes empezar con «Análisis basado
          en reglas», sin configurar una API.
        </p>
      ) : (
        <>
          <label className="ai-history-picker">
            Interpretaciones guardadas
            <select
              aria-label="Interpretaciones guardadas"
              value={current?.id || ""}
              onChange={(event) => setSelected(event.target.value)}
            >
              {state.data.items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.id.slice(0, 8)} · {item.mode_label} ·{" "}
                  {aiStatusLabels[item.status]}
                </option>
              ))}
            </select>
          </label>
          {current && (
            <>
              <div className="ai-state-row">
                <span
                  className={`status-pill ${current.status === "completed" ? "green" : current.status === "failed" ? "red" : "neutral"}`}
                >
                  {activeAI(current) && (
                    <LoaderCircle size={12} className="spinning" />
                  )}
                  {aiStatusLabels[current.status]}
                </span>
                <Link className="run-link" to={`/ai-analyses/${current.id}`}>
                  Abrir interpretación →
                </Link>
                {activeAI(current) && (
                  <button
                    className="button-secondary"
                    disabled={cancelling}
                    onClick={() => void cancel(current.id)}
                  >
                    Cancelar interpretación
                  </button>
                )}
              </div>
              <AIAnalysisResult key={current.id} analysis={current} />
            </>
          )}
          {state.data.total > 5 && (
            <div className="pagination">
              <span>
                {offset + 1}–{offset + state.data.items.length} de{" "}
                {state.data.total}
              </span>
              <div>
                <button
                  className="button-secondary"
                  disabled={!offset}
                  onClick={() => setOffset((value) => value - 5)}
                >
                  Más recientes
                </button>
                <button
                  className="button-secondary"
                  disabled={offset + 5 >= state.data.total}
                  onClick={() => setOffset((value) => value + 5)}
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
      {open && capabilities.state.status === "ready" && (
        <AIConfirmation
          runId={runId}
          capabilities={capabilities.state.data}
          onClose={() => setOpen(false)}
          onCreated={(analysis) => {
            setSelected(analysis.id);
            setOffset(0);
            setOpen(false);
            reload();
          }}
        />
      )}
    </section>
  );
}
