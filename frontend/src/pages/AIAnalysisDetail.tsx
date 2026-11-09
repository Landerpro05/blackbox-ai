import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { usePollingResource } from "../hooks/usePollingResource";
import { activeAI, intelligenceApi } from "../services/intelligence";
import { AIAnalysisResult } from "../components/AIAnalysisResult";
import { aiStatusLabels } from "../components/AIIntelligencePanel";
import { ResourceError, ResourceLoading } from "../components/ResourceFeedback";

export function AIAnalysisDetail() {
  const { id = "" } = useParams();
  const loader = useCallback(
    (signal: AbortSignal) => intelligenceApi.get(id, signal),
    [id],
  );
  const { state, reload } = usePollingResource(loader, activeAI);
  if (state.status === "loading") return <ResourceLoading />;
  if (state.status === "error")
    return (
      <ResourceError
        message={state.message}
        onRetry={reload}
        notFound={state.code === 404}
      />
    );
  return (
    <>
      <Link className="back-link" to={`/runs/${state.data.run_id}`}>
        ← Volver a la ejecución
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">AI INTELLIGENCE</p>
          <h1>
            Interpretación de resultados<span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            {state.data.mode_label} · {aiStatusLabels[state.data.status]}
          </p>
        </div>
        <button className="button-secondary" onClick={reload}>
          Actualizar interpretación
        </button>
      </div>
      <section className="panel reporting-panel">
        <AIAnalysisResult analysis={state.data} />
      </section>
    </>
  );
}
