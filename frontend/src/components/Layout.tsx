import {
  Activity,
  ArrowUpRight,
  Box,
  ChevronRight,
  CircleHelp,
  Code2,
  FileBarChart2,
  FolderKanban,
  LayoutDashboard,
  LockKeyhole,
  Menu,
  Settings2,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { API_BASE_URL } from "../services/api";

export function Layout() {
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
            <strong>Workspace local</strong>
            <span>Entorno de desarrollo</span>
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
          <span className="nav-upcoming" aria-disabled="true">
            <FileBarChart2 size={18} />
            Informes<small>Fase 4</small>
          </span>
          <p className="nav-label second-label">WORKSPACE</p>
          <NavLink to="/settings">
            <Settings2 size={18} />
            Configuración
          </NavLink>
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
            v0.1.0<span>Fase 3 · Motor de testing</span>
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
              {pathname.startsWith("/runs")
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
              title="Workspace local, sin autenticación"
            >
              BB
            </span>
          </div>
        </header>
        <main id="main-content">
          <Outlet />
        </main>
        <footer className="page-footer">
          <span>
            BLACKBOX AI <span className="footer-divider">/</span> Autonomous
            software testing
          </span>
          <span>Desarrollo local · Sin IA configurada</span>
        </footer>
      </div>
    </div>
  );
}
