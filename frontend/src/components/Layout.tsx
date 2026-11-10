import {
  Activity,
  ArrowUpRight,
  Box,
  ChevronRight,
  CircleHelp,
  Code2,
  FileBarChart2,
  FolderKanban,
  FlaskConical,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Settings2,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState, type ReactNode } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { API_BASE_URL } from "../services/api";
import { useAuth } from "./AuthProvider";

export function Layout({ children }: { children?: ReactNode }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [accessError, setAccessError] = useState("");
  const [switching, setSwitching] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const { pathname } = useLocation();
  return (
    <div className="app-shell">
      {menuOpen && (
        <button
          className="sidebar-scrim"
          aria-label="Cerrar navegación"
          onClick={() => setMenuOpen(false)}
        />
      )}
      <aside className={`sidebar ${menuOpen ? "is-open" : ""}`}>
        <a className="brand" href="/" aria-label="BLACKBOX AI, inicio">
          <span className="brand-mark">
            <Box size={24} />
          </span>
          <span>
            BLACKBOX<span className="brand-ai">AI</span>
          </span>
        </a>
        <button
          className="sidebar-close icon-button"
          aria-label="Cerrar menú"
          onClick={() => setMenuOpen(false)}
        >
          <X size={19} />
        </button>
        <div className="workspace-tag">
          <span className="workspace-avatar">B</span>
          <div>
            <label>
              Workspace
              <select
                aria-label="Workspace activo"
                disabled={switching}
                value={auth.workspaceId}
                onChange={(e) => {
                  const id = e.target.value;
                  setSwitching(true);
                  setAccessError("");
                  void auth
                    .select(id)
                    .then(() => navigate("/", { replace: true }))
                    .catch((error) => {
                      setAccessError(
                        error instanceof Error
                          ? error.message
                          : "No se pudo cambiar el workspace.",
                      );
                      setSwitching(false);
                    });
                }}
              >
                <option value="" disabled>
                  Selecciona workspace
                </option>
                {auth.session?.workspaces.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name}
                  </option>
                ))}
              </select>
            </label>
            <span>{auth.role || "Sin membresía"}</span>
          </div>
          <LockKeyhole size={13} />
        </div>
        <p className="nav-label">PLATAFORMA</p>
        <nav
          aria-label="Navegación principal"
          onClick={() => setMenuOpen(false)}
        >
          <NavLink to="/" end>
            <LayoutDashboard size={18} />
            Dashboard
            <ChevronRight size={14} className="nav-arrow" />
          </NavLink>
          <NavLink to="/projects">
            <FolderKanban size={18} />
            Proyectos
          </NavLink>
          <NavLink to="/runs">
            <Activity size={18} />
            Análisis
          </NavLink>
          <NavLink to="/lab">
            <FlaskConical size={18} />
            Testing Lab
          </NavLink>
          <NavLink to="/reports">
            <FileBarChart2 size={18} />
            Informes
          </NavLink>
          <p className="nav-label second-label">WORKSPACE</p>
          <NavLink to="/settings">
            <Settings2 size={18} />
            Configuración
          </NavLink>
          <NavLink to="/account">
            <LockKeyhole size={18} />
            Cuenta y miembros
          </NavLink>
          <button
            className="auth-logout"
            onClick={() =>
              void auth
                .logout()
                .catch((error) =>
                  setAccessError(
                    error instanceof Error
                      ? error.message
                      : "No se pudo cerrar sesión.",
                  ),
                )
            }
          >
            Cerrar sesión
          </button>
        </nav>
        <div className="sidebar-bottom">
          <div className="local-note">
            <ShieldCheck size={19} />
            <strong>Testing responsable</strong>
            <p>Solo aplicaciones propias o con autorización.</p>
          </div>
          <a
            className="docs-link"
            href={`${API_BASE_URL.replace(/\/api\/v1$/, "")}/docs`}
            target="_blank"
            rel="noreferrer"
          >
            <Code2 size={16} />
            API de desarrollo
            <ArrowUpRight size={14} />
          </a>
          <div className="sidebar-version">
            <span className="tiny-dot" />
            v0.1.0<span>Fase 7 · Security & Auth</span>
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-toggle icon-button"
              aria-label="Abrir menú"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen(true)}
            >
              <Menu size={20} />
            </button>
            <span>Workspace</span>
            <ChevronRight size={14} />
            <strong>
              {pathname.startsWith("/account")
                ? "Cuenta y miembros"
                : pathname.startsWith("/lab")
                  ? "Testing Lab"
                  : pathname.startsWith("/ai-analyses")
                    ? "AI Intelligence"
                    : pathname.startsWith("/reports")
                      ? "Informes"
                      : pathname.startsWith("/runs")
                        ? "Análisis"
                        : pathname.startsWith("/projects")
                          ? "Proyectos"
                          : pathname === "/settings"
                            ? "Configuración"
                            : "Dashboard"}
            </strong>
          </div>
          <div className="topbar-right">
            <span className="environment-chip">
              <span className="tiny-dot" />
              LOCAL
            </span>
            <NavLink
              to="/settings"
              className="help-link"
              aria-label="Ayuda y configuración"
            >
              <CircleHelp size={18} />
            </NavLink>
            <span
              className="profile-avatar"
              title={auth.session?.user.email || "Cuenta autenticada"}
            >
              BB
            </span>
          </div>
        </header>
        <main id="main-content">
          {accessError && (
            <div className="inline-alert error-alert" role="alert">
              {accessError}
            </div>
          )}
          {auth.role === "viewer" && (
            <div className="inline-alert" role="status">
              Solo lectura: puedes consultar resultados, informes y evidencias.
              Tu rol no permite modificar datos ni iniciar análisis.
            </div>
          )}
          {children || <Outlet />}
        </main>
        <footer className="page-footer">
          <span>
            BLACKBOX AI <span className="footer-divider">/</span> Autonomous
            software testing
          </span>
          <span>Reglas locales · LLM externo opcional</span>
        </footer>
      </div>
    </div>
  );
}
