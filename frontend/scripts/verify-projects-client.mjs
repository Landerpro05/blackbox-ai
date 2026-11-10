// Exercise the real frontend data client against FastAPI with disposable SQLite.
// This checks HTTP integration, not browser rendering or interaction.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { createServer as createTcpServer } from "node:net";
import { once } from "node:events";
import { createServer } from "vite";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendRoot = resolve(frontendRoot, "../backend");
const python = join(
  backendRoot,
  ".venv",
  process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
);
const temporaryRoot = resolve(tmpdir());
const prefix = join(temporaryRoot, "blackbox-projects-client-");
const directory = await mkdtemp(prefix);
const databasePath = join(directory, "test.db").replaceAll("\\", "/");
const environment = {
  ...process.env,
  BLACKBOX_ENVIRONMENT: "test",
  BLACKBOX_DATABASE_URL: `sqlite:///${databasePath}`,
};
let backend;
let vite;
let backendOutput = "";
const nativeFetch = globalThis.fetch;

function startPython(arguments_) {
  return spawn(python, arguments_, {
    cwd: backendRoot,
    env: environment,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
}

async function stopBackend() {
  // POSIX signal exits keep exitCode=null; cleanup may be called twice.
  if (!backend || backend.exitCode !== null || backend.signalCode !== null)
    return;
  const exited = once(backend, "exit");
  if (process.platform === "win32") {
    // Terminate only the process tree created above (including the venv launcher).
    const terminator = spawn(
      "taskkill.exe",
      ["/PID", String(backend.pid), "/T", "/F"],
      { windowsHide: true, stdio: "ignore" },
    );
    await once(terminator, "exit");
  } else backend.kill("SIGTERM");
  await exited;
}

try {
  const migration = startPython(["-m", "alembic", "upgrade", "head"]);
  let migrationOutput = "";
  migration.stdout.on("data", (value) => {
    migrationOutput += value;
  });
  migration.stderr.on("data", (value) => {
    migrationOutput += value;
  });
  const [migrationCode] = await once(migration, "exit");
  assert.equal(migrationCode, 0, migrationOutput);
  const provision = startPython([
    "-c",
    "import sys; sys.path.insert(0,'tests'); from auth_support import provision_configured_database; provision_configured_database()",
  ]);
  let provisionOutput = "";
  provision.stderr.on("data", (value) => {
    provisionOutput += value;
  });
  assert.equal((await once(provision, "exit"))[0], 0, provisionOutput);

  const reservation = createTcpServer();
  reservation.listen(0, "127.0.0.1");
  await once(reservation, "listening");
  const port = reservation.address().port;
  await new Promise((resolveClose, reject) =>
    reservation.close((error) => (error ? reject(error) : resolveClose())),
  );
  const apiBase = `http://127.0.0.1:${port}/api/v1`;
  backend = startPython([
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    String(port),
    "--workers",
    "1",
  ]);
  backend.stdout.on("data", (value) => {
    backendOutput += value;
  });
  backend.stderr.on("data", (value) => {
    backendOutput += value;
  });
  let healthy = false;
  for (let attempt = 0; attempt < 100; attempt++) {
    if (backend.exitCode !== null) throw new Error(backendOutput);
    try {
      healthy = (
        await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(500) })
      ).ok;
    } catch {
      /* startup in progress */
    }
    if (healthy) break;
    await new Promise((resolveWait) => setTimeout(resolveWait, 100));
  }
  assert.ok(healthy, `Backend did not become ready. ${backendOutput}`);
  process.env.VITE_API_BASE_URL = apiBase;
  vite = await createServer({
    root: frontendRoot,
    server: { middlewareMode: true, hmr: false },
    logLevel: "error",
  });
  const { projectsApi } = await vite.ssrLoadModule("/src/services/projects.ts");
  const { ApiError, fetchOverview } = await vite.ssrLoadModule(
    "/src/services/api.ts",
  );
  const authenticated = await nativeFetch(`${apiBase}/auth/login`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Origin: new URL(apiBase).origin,
      "X-Blackbox-Request": "1",
    },
    body: JSON.stringify({
      email: "owner@example.com",
      password: "Fase7-pruebas-012345!",
    }),
  });
  assert.equal(authenticated.status, 200);
  const identity = await authenticated.json();
  const cookie = authenticated.headers
    .getSetCookie()
    .map((value) => value.split(";", 1)[0])
    .join("; ");
  const { setSessionContext } = await vite.ssrLoadModule(
    "/src/services/session.ts",
  );
  setSessionContext(identity.csrf_token, identity.active_workspace_id);
  globalThis.fetch = (input, options = {}) => {
    const headers = new Headers(options.headers);
    if (String(input).startsWith(apiBase)) {
      headers.set("Cookie", cookie);
      headers.set("Origin", new URL(apiBase).origin);
    }
    return nativeFetch(input, { ...options, headers });
  };

  assert.equal((await projectsApi.list(0)).total, 0);
  const created = await projectsApi.create({
    name: "Client integration",
    description: "Disposable test",
    base_url: "http://127.0.0.1:9",
  });
  assert.equal(created.base_url, "http://127.0.0.1:9/");
  assert.equal(
    (await projectsApi.get(created.id)).description,
    "Disposable test",
  );
  assert.equal((await projectsApi.list(0)).total, 1);
  const updated = await projectsApi.update(created.id, {
    description: "Updated from TypeScript",
  });
  assert.equal(updated.description, "Updated from TypeScript");
  assert.equal(updated.name, created.name);
  assert.equal(
    (await fetchOverview(new AbortController().signal)).dashboard.metrics
      .projects,
    1,
  );
  await assert.rejects(
    projectsApi.create({ name: " ", description: "", base_url: "invalid" }),
    (error) =>
      error instanceof ApiError &&
      error.status === 422 &&
      !!error.fields.name &&
      !!error.fields.base_url,
  );
  assert.equal(await projectsApi.delete(created.id), undefined);
  assert.equal((await projectsApi.list(0)).total, 0);
  await assert.rejects(
    projectsApi.get(created.id),
    (error) => error instanceof ApiError && error.status === 404,
  );
  assert.equal(
    (await fetchOverview(new AbortController().signal)).dashboard.metrics
      .projects,
    0,
  );
  console.log(
    "PASS: frontend client create/list/detail/PATCH/DELETE, validation, 404 and dashboard synchronization.",
  );
  await stopBackend();
  await assert.rejects(projectsApi.list(0), /No se puede conectar con FastAPI/);
  console.log(
    "PASS: frontend client reports an unavailable backend. Temporary data only.",
  );
} finally {
  globalThis.fetch = nativeFetch;
  await vite?.close();
  await stopBackend();
  const target = resolve(directory);
  if (
    dirname(target) !== temporaryRoot ||
    !target.startsWith(prefix) ||
    !target.startsWith(`${temporaryRoot}${sep}`)
  ) {
    throw new Error(
      "Temporary cleanup target is outside the expected directory.",
    );
  }
  await rm(target, { recursive: true, force: true });
}
