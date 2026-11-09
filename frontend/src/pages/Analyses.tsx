import { RunHistory } from "../components/RunHistory";

export function Analyses() {
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MOTOR DE TESTING</p>
          <h1>
            Análisis<span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            Historial de ejecuciones de tu workspace.
          </p>
        </div>
      </div>
      <RunHistory />
    </>
  );
}
