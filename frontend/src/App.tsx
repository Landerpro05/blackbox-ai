import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Dashboard } from "./pages/Dashboard";
import { Settings } from "./pages/Settings";
import { Projects } from "./pages/Projects";
import { NewProject, EditProject } from "./pages/ProjectEditor";
import { ProjectDetail } from "./pages/ProjectDetail";
import { RunDetail } from "./pages/RunDetail";
import { Analyses } from "./pages/Analyses";
import { AIAnalysisDetail } from "./pages/AIAnalysisDetail";
import { TestingLab } from "./pages/TestingLab";

export default function App() {
  return (
    <BrowserRouter>
      <a href="#main-content" className="skip-link">
        Saltar al contenido
      </a>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="settings" element={<Settings />} />
          <Route path="lab" element={<TestingLab />} />
          <Route path="projects" element={<Projects />} />
          <Route path="projects/new" element={<NewProject />} />
          <Route path="projects/:id" element={<ProjectDetail />} />
          <Route path="projects/:id/edit" element={<EditProject />} />
          <Route path="runs" element={<Analyses />} />
          <Route path="reports" element={<Analyses reports />} />
          <Route path="runs/:id" element={<RunDetail />} />
          <Route path="ai-analyses/:id" element={<AIAnalysisDetail />} />
          <Route
            path="*"
            element={
              <div className="panel error-panel">
                <h1>Página no encontrada</h1>
                <p>Esta dirección no existe en el workspace.</p>
                <Link className="button-primary" to="/">
                  Volver al dashboard
                </Link>
              </div>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
