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
import { AuthProvider, useAuth } from "./components/AuthProvider";
import { Login } from "./pages/Login";
import { Account } from "./pages/Account";
import { Navigate, useLocation } from "react-router-dom";

function ProtectedLayout() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.loading)
    return (
      <div className="auth-shell" role="status">
        Comprobando sesión…
      </div>
    );
  if (!auth.session) return <Navigate to="/login" replace />;
  if (!auth.workspaceId && location.pathname !== "/account")
    return <Navigate to="/account" replace />;
  if (
    !auth.canWrite &&
    (location.pathname === "/projects/new" ||
      location.pathname.endsWith("/edit"))
  )
    return (
      <Layout>
        <div className="panel error-panel" role="alert">
          Acceso denegado: tu rol es de solo lectura.{" "}
          <Link to="/">Volver al dashboard</Link>
        </div>
      </Layout>
    );
  return (
    <Layout key={`${auth.session.user.id}/${auth.workspaceId}/${auth.role}`} />
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <a href="#main-content" className="skip-link">
          Saltar al contenido
        </a>
        <Routes>
          <Route path="login" element={<Login />} />
          <Route element={<ProtectedLayout />}>
            <Route path="account" element={<Account />} />
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
    </AuthProvider>
  );
}
