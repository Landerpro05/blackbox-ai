import { RunHistory } from "../components/RunHistory";
import { ComparisonPanel } from "../components/ComparisonPanel";

export function Analyses({ reports = false }: { reports?: boolean }) {
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MOTOR DE TESTING</p>
          <h1>
            {reports ? "Informes y regresiones" : "Análisis"}
            <span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            Historial, exportaciones y comparación de resultados reales de tu
            workspace.
          </p>
        </div>
      </div>
      <ComparisonPanel />
      <RunHistory />
    </>
  );
}
