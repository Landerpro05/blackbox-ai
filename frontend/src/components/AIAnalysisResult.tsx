import { useState } from "react";
import { Link } from "react-router-dom";
import { Copy, ExternalLink } from "lucide-react";
import type { AIAnalysis } from "../types/intelligence";
import { evidenceUrl } from "../services/runs";
import { formatDate } from "../services/format";

const confidence = { low: "Baja", medium: "Media", high: "Alta" };
export function AIAnalysisResult({ analysis }: { analysis: AIAnalysis }) {
  const [copied, setCopied] = useState(-1);
  const [copyError, setCopyError] = useState("");
  const result = analysis.result;
  const anchor = (id: string) => `ai-${analysis.id}-${id}`;
  const citations = (ids: string[]) => (
    <div className="ai-citations">
      {ids.map((id) => (
        <a
          key={id}
          href={`#${anchor(id)}`}
          onClick={() =>
            document
              .getElementById(anchor(id))
              ?.closest("details")
              ?.setAttribute("open", "")
          }
        >
          {id.split(":")[0]}:{id.split(":")[1]?.slice(0, 8)}
        </a>
      ))}
    </div>
  );
  const steps = (items: string[]) => (
    <ul>
      {items.map((item, index) => (
        <li key={index}>{item}</li>
      ))}
    </ul>
  );
  const copy = async (code: string, index: number) => {
    setCopyError("");
    try {
      await navigator.clipboard.writeText(code);
      setCopied(index);
    } catch {
      setCopyError(
        "No se pudo acceder al portapapeles. Selecciona y copia el código manualmente.",
      );
    }
  };
  return (
    <div className="ai-result">
      <p className="report-note">
        {analysis.mode_label} · {analysis.provider} / {analysis.model} ·{" "}
        {formatDate(analysis.created_at)}
      </p>
      <section className="ai-observed">
        <h3>Qué se ha detectado · Hechos observados</h3>
        <dl className="report-facts">
          <div>
            <dt>Páginas registradas</dt>
            <dd>{analysis.evidence.summary.pages}</dd>
          </div>
          <div>
            <dt>Incidencias registradas</dt>
            <dd>{analysis.evidence.summary.issues}</dd>
          </div>
          <div>
            <dt>Grupos deterministas incluidos</dt>
            <dd>{analysis.evidence.groups.length}</dd>
          </div>
        </dl>
        <p className="report-note">
          Contexto limitado: {analysis.evidence.omitted_issues} incidencias y{" "}
          {analysis.evidence.omitted_pages} páginas omitidas. Mensajes en
          cuarentena: {analysis.evidence.quarantined_messages}.
        </p>
        <details>
          <summary>
            Evidencias utilizadas ({analysis.evidence.issues.length}{" "}
            incidencias)
          </summary>
          <div className="ai-evidence-list">
            {analysis.evidence.issues.map((issue) => (
              <article key={issue.id} id={anchor(issue.id)}>
                <strong>{issue.title}</strong>
                <span className="issue-kind">
                  {issue.type} · {issue.severity}
                </span>
                <p className="issue-url">{issue.url}</p>
                <p>{issue.message}</p>
                <small>{issue.id}</small>
                {issue.screenshot_page_id && (
                  <a
                    className="run-link"
                    href={evidenceUrl(
                      `/runs/${analysis.run_id}/pages/${issue.screenshot_page_id}/screenshot`,
                    )}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Ver captura local <ExternalLink size={12} />
                  </a>
                )}
              </article>
            ))}
          </div>
        </details>
        <details>
          <summary>Páginas, tiempos y agrupaciones</summary>
          {analysis.evidence.pages.map((page) => (
            <p key={page.id} id={anchor(page.id)}>
              {page.url} · HTTP {page.status_code ?? "sin respuesta"} ·{" "}
              {page.load_time_ms} ms
            </p>
          ))}
          {analysis.evidence.groups.map((group) => (
            <div key={group.fingerprint}>
              <p>
                Grupo por reglas · {group.count} registros ·{" "}
                {group.fingerprint.slice(0, 12)}
              </p>
              {citations(group.evidence_ids)}
            </div>
          ))}
          {analysis.evidence.history && (
            <div id={anchor(analysis.evidence.history.id)}>
              <Link
                className="run-link"
                to={`/runs/${analysis.evidence.history.base_run_id}`}
              >
                Ejecución anterior{" "}
                {analysis.evidence.history.base_run_id.slice(0, 8)}
              </Link>
              <p>
                Comparación heurística{" "}
                {analysis.evidence.history.partial
                  ? "parcial"
                  : "con cobertura revisitada"}
                :{" "}
                {Object.entries(analysis.evidence.history.counts)
                  .map(([key, value]) => `${key}: ${value}`)
                  .join(" · ")}
              </p>
            </div>
          )}
        </details>
      </section>
      {result && (
        <>
          <div className="ai-summary">
            <h3>
              {analysis.mode === "rules"
                ? "Resumen basado en reglas"
                : "Resumen interpretativo del modelo"}
            </h3>
            <p>{result.summary}</p>
            <p className="report-note">
              Las posibles causas son hipótesis sin confirmar. No se han
              aplicado cambios ni ejecutado las propuestas.
            </p>
          </div>
          <div className="ai-findings">
            {result.findings.map((finding, index) => (
              <article className="ai-finding" key={index}>
                <span className="status-pill neutral">
                  Hipótesis sin confirmar · Confianza{" "}
                  {confidence[finding.confidence]}
                </span>
                <h3>Posibles causas</h3>
                <p>{finding.hypothesis}</p>
                {citations(finding.evidence_ids)}
                <div className="ai-diagnosis-grid">
                  <div>
                    <h4>Cómo investigarlo</h4>
                    {steps(finding.diagnostic_steps)}
                  </div>
                  <div>
                    <h4>Posible solución</h4>
                    {steps(finding.recommendations)}
                  </div>
                </div>
                <h4>Información insuficiente y límites</h4>
                {steps(finding.limitations)}
              </article>
            ))}
          </div>
          {!result.findings.length && (
            <p className="report-note">
              Sin hipótesis justificadas con la evidencia disponible.
            </p>
          )}
          {result.hypothetical_relations.length > 0 && (
            <div className="ai-summary">
              <h3>Relaciones propuestas por el modelo · Hipotéticas</h3>
              {result.hypothetical_relations.map((relation, index) => (
                <article key={index}>
                  <p>{relation.hypothesis}</p>
                  {citations(relation.evidence_ids)}
                </article>
              ))}
            </div>
          )}
          <h3>Recomendaciones</h3>
          {steps(result.recommendations)}
          <h3>Tests Playwright propuestos</h3>
          <p className="report-note">
            Plantillas de código para revisión manual. Sustituye BASE_URL por un
            entorno autorizado. No se ejecutan desde BLACKBOX AI.
          </p>
          {result.suggested_tests.map((test, index) => (
            <article className="ai-test" key={index}>
              <h4>Prueba recomendada: {test.objective}</h4>
              {citations(test.evidence_ids)}
              <details>
                <summary>Condiciones, acciones y aserciones</summary>
                <h4>Condiciones previas</h4>
                {steps(test.preconditions)}
                <h4>Acciones propuestas</h4>
                {steps(test.actions)}
                <h4>Aserciones propuestas</h4>
                {steps(test.assertions)}
                <h4>Limitaciones</h4>
                {steps(test.limitations)}
              </details>
              <div className="ai-code-toolbar">
                <span>Python · Propuesta no ejecutada</span>
                <button
                  className="button-secondary"
                  onClick={() => void copy(test.code, index)}
                >
                  <Copy size={13} />
                  {copied === index ? "Copiado" : "Copiar código"}
                </button>
              </div>
              <pre className="ai-code">
                <code>{test.code}</code>
              </pre>
            </article>
          ))}
          {!result.suggested_tests.length && (
            <p className="report-note">
              No hay una plantilla compatible con las incidencias incluidas. No
              se han inventado selectores o interacciones.
            </p>
          )}
          {copyError && (
            <p className="inline-alert error-alert" role="alert">
              {copyError}
            </p>
          )}
          <h3>Limitaciones del análisis</h3>
          {steps(result.limitations)}
        </>
      )}
      {analysis.mode === "llm" && (
        <p className="report-note">
          Reserva estimada: {analysis.reserved_tokens} tokens,{" "}
          {analysis.reserved_cost_usd === null
            ? "sin tarifa configurada"
            : `${analysis.reserved_cost_usd} USD`}
          . Estimación conservadora, no factura. Uso comunicado por proveedor:{" "}
          {analysis.actual_input_tokens ?? "sin datos"} entrada /{" "}
          {analysis.actual_output_tokens ?? "sin datos"} salida.
        </p>
      )}
      {analysis.error_message && (
        <p className="inline-alert error-alert" role="alert">
          {analysis.error_message}
        </p>
      )}
    </div>
  );
}
