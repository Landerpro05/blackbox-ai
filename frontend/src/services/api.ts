import type { DashboardResponse, HealthResponse } from "../types/api";
import { sessionHeaders, workspaceSignal } from "./session";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000/api/v1"
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public fields: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function requestResponse(
  path: string,
  options: RequestInit = {},
  timeoutMs = 10_000,
): Promise<Response> {
  const signal = options.signal;
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = AbortSignal.any([
    timeout,
    ...(signal ? [signal] : []),
    ...(!path.startsWith("/auth/") ? [workspaceSignal()] : []),
  ]);
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: combined,
      cache: "no-store",
      credentials: "include",
      headers: {
        Accept: "application/json",
        ...sessionHeaders(),
        ...(!["GET", "HEAD"].includes(options.method || "GET")
          ? { "Content-Type": "application/json" }
          : {}),
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
      if (
        response.status === 401 &&
        !["/auth/login", "/auth/register", "/auth/session"].includes(path) &&
        typeof window !== "undefined"
      )
        window.dispatchEvent(new Event("blackbox:session-expired"));
      const body: unknown = await response.json().catch(() => null);
      const detail =
        body && typeof body === "object" && "detail" in body
          ? body.detail
          : null;
      const fields: Record<string, string> = {};
      if (response.status === 422 && Array.isArray(detail)) {
        for (const error of detail) {
          if (
            error &&
            typeof error === "object" &&
            Array.isArray(error.loc) &&
            typeof error.msg === "string"
          ) {
            const field = error.loc[error.loc.length - 1];
            if (typeof field === "string")
              fields[field] = error.msg.replace(/^Value error, /, "");
          }
        }
      }
      const safeDetail =
        typeof detail === "string" &&
        [401, 403, 404, 409, 422, 429].includes(response.status)
          ? detail
          : null;
      const message =
        safeDetail ??
        (response.status === 422
          ? "Revisa los campos del formulario."
          : response.status === 404
            ? "Proyecto no encontrado."
            : response.status === 503
              ? "El servicio no está disponible. Comprueba el backend y las migraciones."
              : "No se pudo completar la operación. Inténtalo de nuevo.");
      throw new ApiError(message, response.status, fields);
    }
    return response;
  } catch (error) {
    if (
      combined.aborted &&
      !signal?.aborted &&
      !workspaceSignal().aborted &&
      !(error instanceof DOMException && error.name === "AbortError")
    )
      throw new Error(
        `La API no ha respondido en ${timeoutMs / 1000} segundos. Comprueba que FastAPI está en ejecución.`,
      );
    if (error instanceof TypeError)
      throw new Error(
        "No se puede conectar con FastAPI. Comprueba el servidor, la URL de la API y CORS.",
      );
    throw error;
  }
}

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await requestResponse(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function fetchOverview(signal: AbortSignal) {
  const [health, dashboard] = await Promise.all([
    request<HealthResponse>("/health", { signal }),
    request<DashboardResponse>("/dashboard", { signal }),
  ]);
  return { health, dashboard };
}
