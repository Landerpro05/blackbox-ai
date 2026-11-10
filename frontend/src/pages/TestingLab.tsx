import { useCallback, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { FlaskConical } from "lucide-react";
import { useResource } from "../hooks/useResource";
import { request } from "../services/api";
import {
  labApi,
  caseLabels,
  type CaseType,
  type Definition,
  type EnvironmentInput,
  type Suite,
  type SuiteCase,
} from "../services/lab";
import { formatDate } from "../services/format";
import { runLabels } from "../services/runs";
import type { ProjectList } from "../types/api";
import { ResourceError, ResourceLoading } from "../components/ResourceFeedback";

type Action = (work: () => Promise<unknown>, message: string) => Promise<void>;
const defaults = {
  max_pages: 10,
  max_depth: 2,
  navigation_timeout_seconds: 15,
  timeout_seconds: 120,
  max_requests: 100,
};
const emptyEnvironment: EnvironmentInput = {
  name: "",
  kind: "local",
  base_url: "http://127.0.0.1:3000",
  limits: defaults,
};

function Pager({
  offset,
  total,
  size = 20,
  change,
}: {
  offset: number;
  total: number;
  size?: number;
  change: (value: number) => void;
}) {
  return (
    <div className="lab-actions">
      <button
        className="button-secondary"
        disabled={!offset}
        onClick={() => change(Math.max(0, offset - size))}
      >
        Anterior
      </button>
      <span>
        {total ? offset + 1 : 0}–{Math.min(offset + size, total)} de {total}
      </span>
      <button
        className="button-secondary"
        disabled={offset + size >= total}
        onClick={() => change(offset + size)}
      >
        Siguiente
      </button>
    </div>
  );
}

function Environments({
  project,
  action,
  busy,
  revision,
}: {
  project: string;
  action: Action;
  busy: boolean;
  revision: number;
}) {
  const [offset, setOffset] = useState(0);
  const loader = useCallback(
    (signal: AbortSignal) => labApi.environments(project, offset, signal),
    [project, offset, revision],
  );
  const { state, reload } = useResource(loader);
  const [editing, setEditing] = useState<string>();
  const [form, setForm] = useState<EnvironmentInput>(emptyEnvironment);
  const [consent, setConsent] = useState<string>();
  const [removing, setRemoving] = useState<string>();
  const save = (event: FormEvent) => {
    event.preventDefault();
    void action(async () => {
      await labApi.saveEnvironment(project, form, editing);
      setEditing(undefined);
      setForm(emptyEnvironment);
    }, "Entorno guardado.");
  };
  return (
    <section className="panel lab-section">
      <h2>Entornos</h2>
      <p className="muted">
        Registrar un entorno no realiza conexiones. La disponibilidad requiere
        autorización explícita.
      </p>
      <form className="lab-form" onSubmit={save}>
        <label>
          Nombre del entorno
          <input
            required
            maxLength={120}
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
        </label>
        <label>
          Tipo
          <select
            aria-label="Tipo"
            value={form.kind}
            onChange={(e) => {
              const kind = e.target.value as "local" | "demo";
              setForm({
                ...form,
                kind,
                base_url:
                  kind === "demo"
                    ? "http://blackbox-demo.invalid/"
                    : "http://127.0.0.1:3000",
              });
            }}
          >
            <option value="local">Desarrollo local controlado</option>
            <option value="demo">Demo integrada</option>
          </select>
        </label>
        <label className="lab-wide">
          URL base del entorno
          <input
            required
            type="url"
            maxLength={2048}
            value={form.base_url}
            onChange={(e) => setForm({ ...form, base_url: e.target.value })}
          />
        </label>
        <details className="lab-wide">
          <summary>Límites de ejecución</summary>
          <div className="lab-form">
            {Object.entries(defaults).map(([key]) => (
              <label key={key}>
                {
                  (
                    {
                      max_pages: "Páginas",
                      max_depth: "Profundidad",
                      navigation_timeout_seconds: "Timeout navegación (s)",
                      timeout_seconds: "Timeout global (s)",
                      max_requests: "Solicitudes",
                    } as Record<string, string>
                  )[key]
                }
                <input
                  type="number"
                  required
                  min={key === "max_depth" ? 0 : 1}
                  max={
                    (
                      {
                        max_pages: 20,
                        max_depth: 3,
                        navigation_timeout_seconds: 30,
                        timeout_seconds: 180,
                        max_requests: 200,
                      } as Record<string, number>
                    )[key]
                  }
                  value={form.limits[key as keyof typeof defaults]}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      limits: { ...form.limits, [key]: Number(e.target.value) },
                    })
                  }
                />
              </label>
            ))}
          </div>
        </details>
        <div className="lab-actions lab-wide">
          <button className="button-primary" disabled={busy}>
            {editing ? "Guardar entorno" : "Crear entorno"}
          </button>
          {editing && (
            <button
              className="button-secondary"
              type="button"
              onClick={() => {
                setEditing(undefined);
                setForm(emptyEnvironment);
              }}
            >
              Descartar edición
            </button>
          )}
        </div>
      </form>
      {state.status === "loading" ? (
        <ResourceLoading label="Cargando entornos…" />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : (
        <>
          <div className="lab-list">
            {!state.data.items.length && (
              <p>Aún no hay entornos en este proyecto.</p>
            )}
            {state.data.items.map((env) => (
              <article key={env.id} className="lab-item">
                <div className="lab-row">
                  <div>
                    <strong>{env.name}</strong>
                    <p>{env.base_url}</p>
                    <small>Origen: {env.authorized_origin}</small>
                    <p>
                      Configuración: {env.configuration_state} · Disponibilidad:{" "}
                      {env.last_check_status || "Sin comprobar"}
                      {env.last_checked_at &&
                        ` · ${formatDate(env.last_checked_at)}`}
                    </p>
                  </div>
                  <div className="lab-actions">
                    <button
                      className="button-secondary"
                      disabled={busy}
                      onClick={() => {
                        setEditing(env.id);
                        setForm({
                          name: env.name,
                          kind: env.kind,
                          base_url: env.base_url,
                          limits: env.limits,
                        });
                      }}
                    >
                      Editar entorno
                    </button>
                    <button
                      className="button-secondary"
                      disabled={busy}
                      onClick={() => setConsent(env.id)}
                    >
                      Comprobar
                    </button>
                    <button
                      className="button-danger"
                      disabled={busy}
                      onClick={() => setRemoving(env.id)}
                    >
                      Eliminar entorno
                    </button>
                  </div>
                </div>
                {consent === env.id && (
                  <div className="inline-alert">
                    <p>
                      Autorizo una solicitud GET al catálogo controlado en{" "}
                      <strong>{env.authorized_origin}</strong>.
                    </p>
                    <button
                      className="button-primary"
                      disabled={busy}
                      onClick={() =>
                        void action(async () => {
                          const result = await labApi.checkEnvironment(env);
                          setConsent(undefined);
                          if (result.last_check_status !== "verified")
                            throw new Error(
                              "El catálogo no está disponible o su contenido no coincide con esta versión.",
                            );
                        }, "Catálogo verificado.")
                      }
                    >
                      Autorizar comprobación
                    </button>
                    <button
                      className="button-secondary"
                      onClick={() => setConsent(undefined)}
                    >
                      Volver
                    </button>
                  </div>
                )}
                {removing === env.id && (
                  <div
                    role="alertdialog"
                    aria-label="Confirmar eliminación de entorno"
                  >
                    <p>
                      ¿Eliminar {env.name}? Se conserva el destino de las
                      ejecuciones anteriores.
                    </p>
                    <button
                      className="button-danger"
                      disabled={busy}
                      onClick={() =>
                        void action(async () => {
                          await labApi.deleteEnvironment(env.id);
                          setRemoving(undefined);
                        }, "Entorno eliminado.")
                      }
                    >
                      Confirmar eliminación
                    </button>
                    <button
                      className="button-secondary"
                      onClick={() => setRemoving(undefined)}
                    >
                      Volver
                    </button>
                  </div>
                )}
              </article>
            ))}
          </div>
          <Pager offset={offset} total={state.data.total} change={setOffset} />
        </>
      )}
    </section>
  );
}

function CaseEditor({
  suite,
  initial,
  action,
  busy,
  close,
  nextPosition,
}: {
  suite: string;
  initial?: SuiteCase;
  action: Action;
  busy: boolean;
  close: () => void;
  nextPosition: number;
}) {
  const [name, setName] = useState(initial?.name || "");
  const [position, setPosition] = useState(initial?.position ?? nextPosition);
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [definition, setDefinition] = useState<Definition>(
    initial?.definition || {
      type: "http_status",
      path: "/about",
      minimum: 200,
      maximum: 200,
    },
  );
  const update = (data: Partial<Definition>) =>
    setDefinition({ ...definition, ...data });
  const changeType = (type: CaseType) =>
    setDefinition({
      type,
      path: definition.path,
      ...(type === "http_status"
        ? { minimum: 200, maximum: 200 }
        : type === "title"
          ? { expected_title: "" }
          : type === "element_exists"
            ? { selector: "h1" }
            : type === "text_visible"
              ? { text: "" }
              : type === "navigate"
                ? { destination: "/about" }
                : {}),
    });
  return (
    <form
      className="lab-form lab-editor"
      aria-label="Editor de caso"
      onSubmit={(e) => {
        e.preventDefault();
        void action(async () => {
          await labApi.saveCase(
            suite,
            { name, position, enabled, definition },
            initial?.id,
          );
          close();
        }, "Caso guardado.");
      }}
    >
      <label>
        Nombre del caso
        <input
          required
          maxLength={120}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label>
        Tipo de prueba
        <select
          aria-label="Tipo de prueba"
          value={definition.type}
          onChange={(e) => changeType(e.target.value as CaseType)}
        >
          {Object.entries(caseLabels).map(([key, value]) => (
            <option key={key} value={key}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label>
        Ruta de página
        <input
          required
          maxLength={512}
          value={definition.path}
          onChange={(e) => update({ path: e.target.value })}
        />
      </label>
      <label>
        Orden (0–99)
        <input
          required
          type="number"
          min={0}
          max={99}
          value={position}
          onChange={(e) => setPosition(Number(e.target.value))}
        />
      </label>
      {definition.type === "http_status" && (
        <>
          {(["minimum", "maximum"] as const).map((key) => (
            <label key={key}>
              {key === "minimum" ? "Estado mínimo" : "Estado máximo"}
              <input
                required
                type="number"
                min={100}
                max={599}
                value={definition[key]}
                onChange={(e) => update({ [key]: Number(e.target.value) })}
              />
            </label>
          ))}
        </>
      )}
      {definition.type === "title" && (
        <label>
          Título esperado
          <input
            required
            maxLength={200}
            value={definition.expected_title}
            onChange={(e) => update({ expected_title: e.target.value })}
          />
        </label>
      )}
      {definition.type === "element_exists" && (
        <label>
          Selector simple
          <input
            required
            maxLength={100}
            value={definition.selector}
            onChange={(e) => update({ selector: e.target.value })}
          />
          <small>Etiqueta, #id, .clase o [data-testid="valor"]</small>
        </label>
      )}
      {definition.type === "text_visible" && (
        <label>
          Texto esperado
          <input
            required
            maxLength={300}
            value={definition.text}
            onChange={(e) => update({ text: e.target.value })}
          />
        </label>
      )}
      {definition.type === "navigate" && (
        <label>
          Ruta de destino
          <input
            required
            maxLength={512}
            value={definition.destination}
            onChange={(e) => update({ destination: e.target.value })}
          />
        </label>
      )}
      <label className="lab-checkbox">
        <input
          type="checkbox"
          checked={enabled}
          onChange={(e) => setEnabled(e.target.checked)}
        />
        Caso habilitado
      </label>
      <div className="lab-actions lab-wide">
        <button className="button-primary" disabled={busy}>
          Guardar caso
        </button>
        <button className="button-secondary" type="button" onClick={close}>
          Cerrar editor
        </button>
      </div>
    </form>
  );
}

function SuiteWorkspace({
  suite,
  project,
  revision,
  busy,
  action,
}: {
  suite: string;
  project: string;
  revision: number;
  busy: boolean;
  action: Action;
}) {
  const navigate = useNavigate();
  const [historyOffset, setHistoryOffset] = useState(0);
  const [envOffset, setEnvOffset] = useState(0);
  const loader = useCallback(
    async (signal: AbortSignal) => {
      const [detail, environments, history] = await Promise.all([
        labApi.suite(suite, signal),
        labApi.environments(project, envOffset, signal),
        labApi.history(suite, historyOffset, signal),
      ]);
      return { detail, environments, history };
    },
    [suite, project, revision, historyOffset, envOffset],
  );
  const { state, reload } = useResource(loader);
  const [editor, setEditor] = useState<SuiteCase | "new">();
  const [remove, setRemove] = useState<string>();
  const [environmentId, setEnvironmentId] = useState("");
  const [consent, setConsent] = useState(false);
  const [analysisId, setAnalysisId] = useState("");
  const [suggestion, setSuggestion] = useState(0);
  const [importName, setImportName] = useState("");
  if (state.status === "loading")
    return <ResourceLoading label="Cargando suite e historial…" />;
  if (state.status === "error")
    return <ResourceError message={state.message} onRetry={reload} />;
  const { detail, environments, history } = state.data;
  const environment = environments.items.find((e) => e.id === environmentId);
  const nextPosition = Math.min(
    99,
    Math.max(-1, ...detail.cases.map((c) => c.position)) + 1,
  );
  return (
    <section className="panel lab-section">
      <div className="panel-heading">
        <div>
          <h2>{detail.name}</h2>
          <p>{detail.description || "Suite declarativa · máximo 20 casos"}</p>
        </div>
        <button
          className="button-primary"
          disabled={busy || detail.cases.length >= 20}
          onClick={() => setEditor("new")}
        >
          Añadir caso
        </button>
      </div>
      {!detail.cases.length && (
        <p>La suite está vacía. Añade un caso para empezar.</p>
      )}
      <div className="lab-list">
        {detail.cases.map((c) => (
          <article className="lab-row" key={c.id}>
            <div>
              <strong>
                {c.position}. {c.name}
              </strong>
              <p>
                {caseLabels[c.definition.type]} · {c.definition.path}
              </p>
            </div>
            <label className="lab-checkbox">
              <input
                aria-label={`Habilitar ${c.name}`}
                type="checkbox"
                disabled={busy}
                checked={c.enabled}
                onChange={(e) =>
                  void action(
                    () => labApi.toggleCase(c.id, e.target.checked),
                    "Estado del caso actualizado.",
                  )
                }
              />
              Habilitado
            </label>
            <div className="lab-actions">
              <button
                className="button-secondary"
                disabled={busy}
                onClick={() => setEditor(c)}
              >
                Editar caso
              </button>
              <button
                className="button-danger"
                disabled={busy}
                onClick={() => setRemove(c.id)}
              >
                Eliminar caso
              </button>
            </div>
            {remove === c.id && (
              <div
                role="alertdialog"
                aria-label="Confirmar eliminación de caso"
              >
                <p>¿Eliminar {c.name}?</p>
                <button
                  className="button-danger"
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      await labApi.deleteCase(c.id);
                      setRemove(undefined);
                    }, "Caso eliminado.")
                  }
                >
                  Confirmar eliminación
                </button>
                <button
                  className="button-secondary"
                  onClick={() => setRemove(undefined)}
                >
                  Volver
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
      {editor && (
        <CaseEditor
          key={editor === "new" ? "new" : editor.id}
          suite={suite}
          initial={editor === "new" ? undefined : editor}
          nextPosition={nextPosition}
          action={action}
          busy={busy}
          close={() => setEditor(undefined)}
        />
      )}
      <div className="lab-editor">
        <h3>Ejecutar suite</h3>
        <label className="lab-field">
          Entorno autorizado
          <select
            aria-label="Entorno autorizado"
            value={environmentId}
            onChange={(e) => {
              setEnvironmentId(e.target.value);
              setConsent(false);
            }}
          >
            <option value="">Selecciona un entorno</option>
            {environments.items.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name} · {e.configuration_state}
              </option>
            ))}
          </select>
        </label>
        <Pager
          offset={envOffset}
          total={environments.total}
          change={(value) => {
            setEnvOffset(value);
            setEnvironmentId("");
            setConsent(false);
          }}
        />
        {environment && (
          <label className="lab-checkbox">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            Autorizo esta ejecución de solo lectura en{" "}
            {environment.authorized_origin}.
          </label>
        )}
        <button
          className="button-primary"
          disabled={
            busy ||
            !environment ||
            !consent ||
            environment.configuration_state !== "ready" ||
            !detail.cases.some((c) => c.enabled)
          }
          onClick={() =>
            environment &&
            void action(async () => {
              const run = await labApi.start(suite, environment);
              setConsent(false);
              navigate(`/runs/${run.id}`);
            }, "Ejecución iniciada.")
          }
        >
          Ejecutar suite autorizada
        </button>
      </div>
      <details className="lab-editor">
        <summary>Importar una sugerencia de IA</summary>
        <p>
          Solo se convierte una plantilla compatible con evidencia del mismo
          proyecto. El caso se guarda deshabilitado para revisarlo. El código
          generado no se ejecuta.
        </p>
        <form
          className="lab-form"
          onSubmit={(e) => {
            e.preventDefault();
            void action(
              () =>
                labApi.importAI(suite, {
                  analysis_id: analysisId,
                  suggestion_index: suggestion,
                  name: importName,
                  position: nextPosition,
                  confirm: true,
                }),
              "Sugerencia convertida; revisa el caso antes de habilitarlo.",
            );
          }}
        >
          <label>
            ID del análisis
            <input
              required
              value={analysisId}
              onChange={(e) => setAnalysisId(e.target.value)}
            />
          </label>
          <label>
            Índice de sugerencia (0–7)
            <input
              required
              type="number"
              min={0}
              max={7}
              value={suggestion}
              onChange={(e) => setSuggestion(Number(e.target.value))}
            />
          </label>
          <label>
            Nombre del caso importado
            <input
              required
              maxLength={120}
              value={importName}
              onChange={(e) => setImportName(e.target.value)}
            />
          </label>
          <label className="lab-checkbox">
            <input required type="checkbox" />
            Confirmo la conversión declarativa
          </label>
          <button
            className="button-secondary"
            disabled={busy || detail.cases.length >= 20}
          >
            Validar e importar
          </button>
        </form>
      </details>
      <h3>Historial de ejecuciones</h3>
      <div className="lab-list">
        {!history.items.length && <p>Todavía no hay ejecuciones.</p>}
        {history.items.map((run) => (
          <Link className="lab-row" key={run.id} to={`/runs/${run.id}`}>
            <strong>{run.id.slice(0, 8)}</strong>
            <span>{runLabels[run.status]}</span>
            <span>{formatDate(run.created_at)}</span>
          </Link>
        ))}
      </div>
      <Pager
        offset={historyOffset}
        total={history.total}
        change={setHistoryOffset}
      />
    </section>
  );
}

function Suites({
  project,
  revision,
  busy,
  action,
}: {
  project: string;
  revision: number;
  busy: boolean;
  action: Action;
}) {
  const [offset, setOffset] = useState(0);
  const loader = useCallback(
    (signal: AbortSignal) => labApi.suites(project, offset, signal),
    [project, offset, revision],
  );
  const { state, reload } = useResource(loader);
  const [selected, setSelected] = useState("");
  const [editing, setEditing] = useState<Suite>();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [remove, setRemove] = useState<string>();
  return (
    <>
      <section className="panel lab-section">
        <h2>Test Suites</h2>
        <form
          className="lab-form"
          onSubmit={(e) => {
            e.preventDefault();
            void action(async () => {
              const result = await labApi.saveSuite(
                project,
                { name, description },
                editing?.id,
              );
              setSelected(result.id);
              setEditing(undefined);
              setName("");
              setDescription("");
            }, "Suite guardada.");
          }}
        >
          <label>
            Nombre de la suite
            <input
              required
              maxLength={120}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label>
            Descripción de la suite
            <input
              maxLength={5000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <div className="lab-actions">
            <button className="button-primary" disabled={busy}>
              {editing ? "Guardar suite" : "Crear suite"}
            </button>
            {editing && (
              <button
                className="button-secondary"
                type="button"
                onClick={() => {
                  setEditing(undefined);
                  setName("");
                  setDescription("");
                }}
              >
                Descartar edición
              </button>
            )}
          </div>
        </form>
        {state.status === "loading" ? (
          <ResourceLoading label="Cargando suites…" />
        ) : state.status === "error" ? (
          <ResourceError message={state.message} onRetry={reload} />
        ) : (
          <>
            <div className="lab-list">
              {!state.data.items.length && (
                <p>Aún no hay suites en este proyecto.</p>
              )}
              {state.data.items.map((s) => (
                <article className="lab-row" key={s.id}>
                  <button
                    className="button-secondary"
                    aria-pressed={selected === s.id}
                    onClick={() => setSelected(s.id)}
                  >
                    {s.name}
                  </button>
                  <div className="lab-actions">
                    <button
                      className="button-secondary"
                      disabled={busy}
                      onClick={() => {
                        setEditing(s);
                        setName(s.name);
                        setDescription(s.description);
                      }}
                    >
                      Editar suite
                    </button>
                    <button
                      className="button-danger"
                      disabled={busy}
                      onClick={() => setRemove(s.id)}
                    >
                      Eliminar suite
                    </button>
                  </div>
                  {remove === s.id && (
                    <div
                      role="alertdialog"
                      aria-label="Confirmar eliminación de suite"
                    >
                      <p>
                        ¿Eliminar {s.name} y sus casos? Los resultados
                        anteriores se conservan.
                      </p>
                      <button
                        className="button-danger"
                        disabled={busy}
                        onClick={() =>
                          void action(async () => {
                            await labApi.deleteSuite(s.id);
                            if (selected === s.id) setSelected("");
                            setRemove(undefined);
                          }, "Suite eliminada.")
                        }
                      >
                        Confirmar eliminación
                      </button>
                      <button
                        className="button-secondary"
                        onClick={() => setRemove(undefined)}
                      >
                        Volver
                      </button>
                    </div>
                  )}
                </article>
              ))}
            </div>
            <Pager
              offset={offset}
              total={state.data.total}
              change={setOffset}
            />
          </>
        )}
      </section>
      {selected && (
        <SuiteWorkspace
          key={selected}
          suite={selected}
          project={project}
          revision={revision}
          action={action}
          busy={busy}
        />
      )}
    </>
  );
}

export function TestingLab() {
  const [params, setParams] = useSearchParams();
  const project = params.get("project") || "";
  const [offset, setOffset] = useState(0);
  const [tab, setTab] = useState("environments");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const loader = useCallback(
    async (signal: AbortSignal) => {
      const [projects, capabilities] = await Promise.all([
        request<ProjectList>(`/projects?limit=20&offset=${offset}`, { signal }),
        labApi.capabilities(signal),
      ]);
      return { projects, capabilities };
    },
    [offset],
  );
  const { state, reload } = useResource(loader);
  const action: Action = async (work, success) => {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await work();
      setMessage(success);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "No se pudo completar la operación.",
      );
    } finally {
      setBusy(false);
      setRevision((v) => v + 1);
    }
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DEVELOPER WORKSPACE</p>
          <h1>
            <FlaskConical size={28} /> Testing Lab
            <span className="heading-dot">.</span>
          </h1>
          <p className="page-description">
            Entornos autorizados, suites declarativas y pruebas reproducibles.
          </p>
        </div>
      </div>
      <div className="inline-alert">
        <p>
          El modo local admite únicamente la aplicación controlada incluida en
          este proyecto. Cada respuesta se verifica antes de llegar al
          navegador. Las aplicaciones arbitrarias y los destinos remotos siguen
          deshabilitados.
        </p>
      </div>
      {state.status === "loading" ? (
        <ResourceLoading label="Cargando laboratorio…" />
      ) : state.status === "error" ? (
        <ResourceError message={state.message} onRetry={reload} />
      ) : (
        <>
          <section className="panel lab-section">
            <label className="lab-field">
              Proyecto del laboratorio
              <select
                aria-label="Proyecto del laboratorio"
                value={project}
                onChange={(e) => {
                  setParams(e.target.value ? { project: e.target.value } : {});
                  setMessage("");
                  setError("");
                }}
              >
                <option value="">Selecciona un proyecto</option>
                {state.data.projects.items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
                {project &&
                  !state.data.projects.items.some((p) => p.id === project) && (
                    <option value={project}>
                      Proyecto seleccionado · {project.slice(0, 8)}
                    </option>
                  )}
              </select>
            </label>
            <Pager
              offset={offset}
              total={state.data.projects.total}
              change={setOffset}
            />
            <p>
              <Link to="/projects/new">Crear proyecto</Link>
            </p>
            <p className="muted">
              Demo:{" "}
              {state.data.capabilities.demo_enabled
                ? "habilitada"
                : "deshabilitada"}{" "}
              · Local:{" "}
              {state.data.capabilities.local_enabled
                ? "habilitado"
                : "deshabilitado por configuración"}
            </p>
            <p className="muted">
              Orígenes locales permitidos:{" "}
              {state.data.capabilities.allowed_origins.join(", ") || "ninguno"}
            </p>
          </section>
          <div
            className="lab-tabs"
            role="group"
            aria-label="Secciones del laboratorio"
          >
            {[
              ["environments", "Entornos"],
              ["suites", "Test Suites"],
              ["ci", "Integración CI/CD"],
            ].map(([key, label]) => (
              <button
                key={key}
                className={tab === key ? "button-primary" : "button-secondary"}
                aria-pressed={tab === key}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
          {busy && <p role="status">Guardando cambios…</p>}
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
          {tab === "ci" ? (
            <section className="panel lab-section">
              <h2>GitHub Actions y CLI</h2>
              <p>
                Workflow versionado:{" "}
                <code>{state.data.capabilities.workflow_path}</code>. Ejecuta
                tests, migraciones, dependencias, build y Chromium contra
                contenido controlado del runner.
              </p>
              <p>
                Estado remoto: sin consultar. Esta pantalla no está conectada a
                los resultados de GitHub. Consulta la pestaña Actions del
                repositorio.
              </p>
              <h3>Aplicación local controlada</h3>
              <pre>python -m app.lab_server --port 3000</pre>
              <p>
                Configura el backend con BLACKBOX_LOCAL_LAB_ENABLED=true y
                BLACKBOX_LOCAL_LAB_ALLOWED_ORIGINS=["http://127.0.0.1:3000"].
                Reinicia el backend y registra ese origen. No registra
                credenciales.
              </p>
              <h3>Demo desde CLI</h3>
              <pre>python -m app.cli demo --authorize --json results.json</pre>
              <h3>Suite existente</h3>
              <pre>
                python -m app.cli test --project PROJECT_ID --suite SUITE_ID
                --environment ENV_ID --origin http://127.0.0.1:3000 --authorize
                --json results.json
              </pre>
              <p>
                Códigos de salida: 0 = casos correctos; 1 = aserciones fallidas;
                2 = configuración o ejecución fallida; 3 = cancelación o timeout
                de espera.
              </p>
              <p>
                Para CI usa --standalone --database una-base-independiente.db y
                habilita únicamente la demo. No necesita claves de IA. El
                workflow no hace push ni merge.
              </p>
            </section>
          ) : project ? (
            tab === "environments" ? (
              <Environments
                key={project}
                project={project}
                revision={revision}
                action={action}
                busy={busy}
              />
            ) : (
              <Suites
                key={project}
                project={project}
                revision={revision}
                action={action}
                busy={busy}
              />
            )
          ) : (
            <section className="panel lab-section">
              <p>
                Selecciona o crea un proyecto para configurar sus entornos y
                suites.
              </p>
            </section>
          )}
        </>
      )}
    </>
  );
}
