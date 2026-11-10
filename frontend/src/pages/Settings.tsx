import { ArrowUpRight, BookOpen, Server, ShieldCheck } from "lucide-react";
import { API_BASE_URL } from "../services/api";

export function Settings() {
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">WORKSPACE</p>
          <h1>
            Configuración<span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            Conexión y alcance de tu entorno de desarrollo.
          </p>
        </div>
      </div>
      <section className="panel settings-panel">
        <div className="panel-heading">
          <div>
            <h2>
              <Server size={18} />
              Conexión con el backend
            </h2>
            <p>Configuración de conexión de solo lectura</p>
          </div>
        </div>
        <div className="settings-body">
          <label>URL de la API</label>
          <code>{API_BASE_URL}</code>
          <p>
            Para cambiarla, edita <code>VITE_API_BASE_URL</code> en{" "}
            <code>frontend/.env</code> y reinicia Vite. Las variables VITE_ son
            públicas: nunca incluyas claves ni contraseñas.
          </p>
          <a
            className="button-secondary"
            href={`${API_BASE_URL.replace(/\/api\/v1$/, "")}/docs`}
            target="_blank"
            rel="noreferrer"
          >
            <BookOpen size={16} />
            Abrir documentación de la API
            <ArrowUpRight size={14} />
          </a>
        </div>
      </section>
      <section className="panel settings-panel">
        <div className="panel-heading">
          <div>
            <h2>
              <ShieldCheck size={18} />
              Alcance actual
            </h2>
            <p>Fase 7 · Autenticación y seguridad</p>
          </div>
        </div>
        <div className="settings-body">
          <p>
            Backend y frontend independientes, base SQLite con migraciones,
            endpoints de salud, dashboard conectado y gestión de proyectos con
            persistencia real.
          </p>
          <p>
            Registrar o editar un proyecto no provoca navegación a su URL. El
            motor Playwright admite la demo integrada y el catálogo local
            verificado del proyecto, requiere activación en el servidor y
            autorización por ejecución. La navegación remota está deshabilitada.
            Los resultados pueden interpretarse con reglas locales o con un LLM
            externo configurado en el backend. El modo externo requiere
            confirmar el proveedor, modelo y envío de evidencias redactadas. Los
            tests propuestos nunca se ejecutan automáticamente.
          </p>
          <p>
            Testing Lab organiza entornos y suites declarativas. Las
            aplicaciones arbitrarias siguen deshabilitadas. Puedes ejecutar las
            suites desde la CLI y verificar el proyecto con GitHub Actions.
          </p>
          <p>
            El acceso requiere una sesión y membresía del workspace. Los
            permisos se verifican en el servidor, con cookies HttpOnly, CSRF y
            sesiones revocables. Usa los servidores en loopback; esta entrega no
            realiza un despliegue público.
          </p>
        </div>
      </section>
    </>
  );
}
