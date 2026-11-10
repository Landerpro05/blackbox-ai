import { MIN_PASSWORD_LENGTH } from "../services/session";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { LockKeyhole, ShieldCheck } from "lucide-react";
import { useAuth } from "../components/AuthProvider";
import { request } from "../services/api";
import type { SessionData } from "../services/session";

export function Login() {
  const auth = useAuth();
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [invitation, setInvitation] = useState("");
  const [workspaceName, setWorkspaceName] = useState("Mi workspace");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (auth.loading)
    return (
      <div className="auth-shell">
        <p role="status">Comprobando sesión…</p>
      </div>
    );
  if (auth.session) return <Navigate to="/" replace />;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const data = await request<SessionData>(
        register ? "/auth/register" : "/auth/login",
        {
          method: "POST",
          body: JSON.stringify({
            email,
            password,
            ...(register ? { invitation, workspace_name: workspaceName } : {}),
          }),
        },
      );
      setPassword("");
      setInvitation("");
      auth.complete(data);
    } catch (caught) {
      setPassword("");
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo completar el acceso.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="auth-shell">
      <section className="panel auth-card">
        <div className="auth-brand">
          <ShieldCheck size={24} />
          <strong>BLACKBOX AI</strong>
          <span>LOCAL WORKSPACE</span>
        </div>
        <h1>{register ? "Crear cuenta" : "Iniciar sesión"}</h1>
        <p>Acceso autenticado a tus proyectos y resultados de testing.</p>
        {(error || auth.error) && (
          <div className="inline-alert error-alert" role="alert">
            {error || auth.error}
          </div>
        )}
        {auth.message && <p role="status">{auth.message}</p>}
        <form className="auth-form" onSubmit={submit}>
          <label>
            Correo electrónico
            <input
              type="email"
              autoComplete="username"
              required
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Contraseña
            <input
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              required
              minLength={register ? MIN_PASSWORD_LENGTH : 1}
              maxLength={128}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {register && (
            <>
              <label>
                Código de invitación
                <input
                  required
                  type="password"
                  autoComplete="off"
                  minLength={32}
                  maxLength={128}
                  value={invitation}
                  onChange={(e) => setInvitation(e.target.value)}
                />
              </label>
              <label>
                Nombre de tu primer workspace
                <input
                  required
                  maxLength={120}
                  value={workspaceName}
                  onChange={(e) => setWorkspaceName(e.target.value)}
                />
              </label>
              <p className="muted">
                El registro requiere una invitación. Para la primera cuenta, el
                administrador local genera un código con{" "}
                <code>python -m app.admin registration-code</code>. Los datos
                históricos se adoptan por separado.
              </p>
            </>
          )}
          <button className="button-primary" disabled={busy}>
            <LockKeyhole size={16} />
            {busy ? "Comprobando…" : register ? "Registrar cuenta" : "Entrar"}
          </button>
        </form>
        <button
          className="button-secondary"
          disabled={busy}
          onClick={() => {
            setRegister(!register);
            setError("");
            setPassword("");
          }}
        >
          {register ? "Volver al login" : "Tengo una invitación"}
        </button>
        <p className="auth-note">
          Sin recuperación por correo. Las cookies de sesión son HttpOnly y las
          operaciones requieren protección CSRF. Este entorno no se despliega
          públicamente.
        </p>
      </section>
    </main>
  );
}
