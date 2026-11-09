import type { DashboardResponse, HealthResponse } from "../types/api";

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

export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const signal = options.signal;
  const timeout = AbortSignal.timeout(10_000);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: combined,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...options.headers,
      },
    });
    if (!response.ok) {
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
        typeof detail === "string" && [403, 404, 409].includes(response.status)
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
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (combined.aborted && !signal?.aborted)
      throw new Error(
        "La API no ha respondido en 10 segundos. Comprueba que FastAPI está en ejecución.",
      );
    if (error instanceof TypeError)
      throw new Error(
        "No se puede conectar con FastAPI. Comprueba el servidor, la URL de la API y CORS.",
      );
    throw error;
  }
}

export async function fetchOverview(signal: AbortSignal) {
  const [health, dashboard] = await Promise.all([
    request<HealthResponse>("/health", { signal }),
    request<DashboardResponse>("/dashboard", { signal }),
  ]);
  return { health, dashboard };
}
