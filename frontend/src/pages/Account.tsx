import { useCallback, useState, type FormEvent } from "react";
import { useAuth } from "../components/AuthProvider";
import { useResource } from "../hooks/useResource";
import { request } from "../services/api";
import { formatDate } from "../services/format";
import { ResourceError, ResourceLoading } from "../components/ResourceFeedback";

interface Member {
  user_id: string;
  email: string;
  role: string;
}
interface SessionInfo {
  id: string;
  current: boolean;
  revoked: boolean;
  created_at: string;
  expires_at: string;
  last_seen_at: string;
}
interface Audit {
  id: string;
  event_type: string;
  user_id: string | null;
  resource_id: string | null;
  outcome: string;
  created_at: string;
}

export function Account() {
  const auth = useAuth();
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [name, setName] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteCode, setInviteCode] = useState("");
  const [acceptCode, setAcceptCode] = useState("");
  const [memberOffset, setMemberOffset] = useState(0);
  const [auditOffset, setAuditOffset] = useState(0);
  const ws = auth.workspaceId;
  const loader = useCallback(
    async (signal: AbortSignal) => {
      const sessions = await request<{ items: SessionInfo[] }>(
        "/auth/sessions",
        { signal },
      );
      const members = ws
        ? await request<{ items: Member[]; total: number }>(
            `/workspaces/${ws}/members?offset=${memberOffset}`,
            { signal },
          )
        : { items: [], total: 0 };
      const audit =
        ws && ["owner", "admin"].includes(auth.role)
          ? await request<{ items: Audit[]; total: number }>(
              `/workspaces/${ws}/audit?offset=${auditOffset}`,
              { signal },
            )
          : { items: [], total: 0 };
      return { sessions, members, audit };
    },
    [ws, auth.role, memberOffset, auditOffset, revision],
  );
  const { state, reload } = useResource(loader);
  const action = async (work: () => Promise<unknown>, success: string) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await work();
      setMessage(success);
      setRevision((v) => v + 1);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo completar la operación.",
      );
    } finally {
      setBusy(false);
    }
  };
  const submit = (
    event: FormEvent,
    work: () => Promise<unknown>,
    success: string,
  ) => {
    event.preventDefault();
    void action(work, success);
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CUENTA Y ACCESO</p>
          <h1>
            Cuenta y workspaces<span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            {auth.session?.user.email} · Rol actual:{" "}
            {auth.role || "Sin workspace seleccionado"}
          </p>
        </div>
      </div>
      {error && (
        <div className="inline-alert error-alert" role="alert">
          {error}
        </div>
      )}
      {message && (
        <div className="inline-alert" role="status">
          {message}
        </div>
      )}
      <section className="panel lab-section">
        <h2>Permisos de tu rol</h2>
        <div className="table-scroll">
          <table className="auth-permissions">
            <thead>
              <tr>
                <th>Rol</th>
                <th>Permisos</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>owner</td>
                <td>
                  Administración de miembros y workspace, gestión operativa, LLM
                  y auditoría.
                </td>
              </tr>
              <tr>
                <td>admin</td>
                <td>
                  Gestión operativa, eliminación de proyectos, LLM y auditoría.
                </td>
              </tr>
              <tr>
                <td>member</td>
                <td>
                  Crear y editar proyectos, gestionar suites/entornos, ejecutar
                  pruebas y reglas. Sin eliminar proyectos ni usar LLM.
                </td>
              </tr>
              <tr>
                <td>viewer</td>
                <td>
                  Consultar resultados, informes, evidencias y configuración.
                  Sin operaciones mutables.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p>El backend verifica tu membresía y permisos en cada solicitud.</p>
      </section>
      <section className="panel lab-section">
        <h2>Cambiar contraseña</h2>
        <form
          className="lab-form"
          onSubmit={(e) =>
            submit(
              e,
              async () => {
                await request("/auth/password", {
                  method: "POST",
                  body: JSON.stringify({
                    current_password: currentPassword,
                    new_password: newPassword,
                  }),
                });
                setCurrentPassword("");
                setNewPassword("");
                auth.expire(
                  "Contraseña actualizada. Todas las sesiones se han revocado; inicia sesión de nuevo.",
                );
              },
              "Contraseña actualizada.",
            )
          }
        >
          <label>
            Contraseña actual
            <input
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
            />
          </label>
          <label>
            Nueva contraseña
            <input
              type="password"
              autoComplete="new-password"
              required
              minLength={12}
              maxLength={128}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
          </label>
          <button className="button-primary" disabled={busy}>
            Actualizar contraseña y revocar sesiones
          </button>
        </form>
      </section>
      <section className="panel lab-section">
        <h2>Workspaces</h2>
        <form
          className="lab-form"
          onSubmit={(e) =>
            submit(
              e,
              async () => {
                await request("/workspaces", {
                  method: "POST",
                  body: JSON.stringify({ name }),
                });
                setName("");
                await auth.refresh();
              },
              "Workspace creado.",
            )
          }
        >
          <label>
            Nombre del nuevo workspace
            <input
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <button className="button-primary" disabled={busy}>
            Crear workspace
          </button>
        </form>
        <form
          className="lab-form"
          onSubmit={(e) =>
            submit(
              e,
              async () => {
                await request("/auth/invitations/accept", {
                  method: "POST",
                  body: JSON.stringify({ invitation: acceptCode }),
                });
                setAcceptCode("");
                await auth.refresh();
              },
              "Invitación aceptada.",
            )
          }
        >
          <label>
            Código para unirme a otro workspace
            <input
              required
              type="password"
              autoComplete="off"
              minLength={32}
              maxLength={128}
              value={acceptCode}
              onChange={(e) => setAcceptCode(e.target.value)}
            />
          </label>
          <button className="button-secondary" disabled={busy}>
            Aceptar invitación
          </button>
        </form>
        <p className="muted">
          Los datos históricos no se asignan automáticamente a tu cuenta. Su
          adopción requiere una operación explícita del administrador local.
        </p>
      </section>
      {state.status === "loading" ? (
        <ResourceLoading label="Cargando acceso y sesiones…" />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : (
        <>
          <section className="panel lab-section">
            <h2>Sesiones</h2>
            <p>
              Expiración absoluta e inactividad; como máximo cinco sesiones
              activas. Se muestran las veinte más recientes.
            </p>
            <div className="lab-list">
              {state.data.sessions.items.map((session) => (
                <article className="lab-row" key={session.id}>
                  <div>
                    <strong>
                      {session.current
                        ? "Sesión actual"
                        : session.id.slice(0, 8)}
                    </strong>
                    <p>
                      Creada {formatDate(session.created_at)} · Expira{" "}
                      {formatDate(session.expires_at)}
                    </p>
                    <small>{session.revoked ? "Revocada" : "Registrada"}</small>
                  </div>
                  <button
                    className="button-danger"
                    disabled={busy || session.revoked}
                    onClick={() =>
                      void action(async () => {
                        await request(`/auth/sessions/${session.id}`, {
                          method: "DELETE",
                        });
                        if (session.current) auth.expire();
                      }, "Sesión revocada.")
                    }
                  >
                    Revocar sesión
                  </button>
                </article>
              ))}
            </div>
          </section>
          {ws && (
            <section className="panel lab-section">
              <h2>Miembros del workspace</h2>
              <div className="lab-list">
                {state.data.members.items.map((member) => (
                  <article className="lab-row" key={member.user_id}>
                    <div>
                      <strong>{member.email}</strong>
                      <p>{member.role}</p>
                    </div>
                    {auth.role === "owner" && (
                      <div className="lab-actions">
                        <label>
                          Rol de {member.email}
                          <select
                            aria-label={`Rol de ${member.email}`}
                            disabled={busy}
                            value={member.role}
                            onChange={(e) => {
                              const role = e.target.value;
                              void action(async () => {
                                await request(
                                  `/workspaces/${ws}/members/${member.user_id}`,
                                  {
                                    method: "PATCH",
                                    body: JSON.stringify({ role }),
                                  },
                                );
                                await auth.refresh();
                              }, "Rol actualizado.");
                            }}
                          >
                            {["owner", "admin", "member", "viewer"].map(
                              (role) => (
                                <option key={role} value={role}>
                                  {role}
                                </option>
                              ),
                            )}
                          </select>
                        </label>
                        <button
                          className="button-danger"
                          disabled={busy}
                          onClick={() => {
                            if (
                              window.confirm(
                                `¿Eliminar la membresía de ${member.email}?`,
                              )
                            )
                              void action(async () => {
                                await request(
                                  `/workspaces/${ws}/members/${member.user_id}`,
                                  { method: "DELETE" },
                                );
                                await auth.refresh();
                              }, "Miembro retirado.");
                          }}
                        >
                          Retirar miembro
                        </button>
                      </div>
                    )}
                  </article>
                ))}
              </div>
              <div className="lab-actions">
                <button
                  className="button-secondary"
                  disabled={!memberOffset}
                  onClick={() =>
                    setMemberOffset(Math.max(0, memberOffset - 50))
                  }
                >
                  Miembros anteriores
                </button>
                <span>{state.data.members.total} miembros</span>
                <button
                  className="button-secondary"
                  disabled={memberOffset + 50 >= state.data.members.total}
                  onClick={() => setMemberOffset(memberOffset + 50)}
                >
                  Miembros siguientes
                </button>
              </div>
              {auth.role === "owner" && (
                <>
                  <h3>Invitación controlada</h3>
                  <form
                    className="lab-form"
                    onSubmit={(e) =>
                      submit(
                        e,
                        async () => {
                          const result = await request<{ invitation: string }>(
                            `/workspaces/${ws}/invitations`,
                            {
                              method: "POST",
                              body: JSON.stringify({
                                email: inviteEmail,
                                role: inviteRole,
                              }),
                            },
                          );
                          setInviteCode(result.invitation);
                        },
                        "Invitación creada; caduca en 24 horas y solo sirve para ese correo.",
                      )
                    }
                  >
                    <label>
                      Correo del invitado
                      <input
                        required
                        type="email"
                        value={inviteEmail}
                        onChange={(e) => setInviteEmail(e.target.value)}
                      />
                    </label>
                    <label>
                      Rol de invitación
                      <select
                        aria-label="Rol de invitación"
                        value={inviteRole}
                        onChange={(e) => setInviteRole(e.target.value)}
                      >
                        {["admin", "member", "viewer"].map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button className="button-primary" disabled={busy}>
                      Crear invitación
                    </button>
                  </form>
                  {inviteCode && (
                    <div className="inline-alert">
                      <label>
                        Código de un solo uso
                        <input readOnly value={inviteCode} />
                      </label>
                      <p>
                        No se envía por correo ni se guarda en el navegador.
                        Compártelo por un canal privado.
                      </p>
                      <button
                        className="button-secondary"
                        onClick={() => setInviteCode("")}
                      >
                        Ocultar código
                      </button>
                    </div>
                  )}
                </>
              )}
            </section>
          )}
          {ws && ["owner", "admin"].includes(auth.role) && (
            <section className="panel lab-section">
              <h2>Auditoría</h2>
              <p>
                Retención local: se purgan eventos antiguos al arrancar, 90 días
                por defecto. Los eventos no incluyen contraseñas, tokens ni
                contextos IA.
              </p>
              <div className="lab-list">
                {!state.data.audit.items.length && (
                  <p>No hay eventos visibles.</p>
                )}
                {state.data.audit.items.map((event) => (
                  <article className="lab-row" key={event.id}>
                    <div>
                      <strong>{event.event_type}</strong>
                      <p>
                        {formatDate(event.created_at)} · {event.outcome}
                      </p>
                      <small>
                        Usuario: {event.user_id || "sistema"} · Recurso:{" "}
                        {event.resource_id || "—"}
                      </small>
                    </div>
                  </article>
                ))}
              </div>
              <div className="lab-actions">
                <button
                  className="button-secondary"
                  disabled={!auditOffset}
                  onClick={() => setAuditOffset(Math.max(0, auditOffset - 50))}
                >
                  Eventos anteriores
                </button>
                <span>{state.data.audit.total} eventos</span>
                <button
                  className="button-secondary"
                  disabled={auditOffset + 50 >= state.data.audit.total}
                  onClick={() => setAuditOffset(auditOffset + 50)}
                >
                  Eventos siguientes
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </>
  );
}
