import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { request } from "../services/api";
import {
  clearSessionContext,
  setSessionContext,
  type SessionData,
} from "../services/session";

interface AuthContextValue {
  session: SessionData | null;
  loading: boolean;
  error: string;
  message: string;
  role: string;
  workspaceId: string;
  canWrite: boolean;
  refresh: () => Promise<void>;
  complete: (data: SessionData) => void;
  logout: () => Promise<void>;
  select: (id: string) => Promise<void>;
  expire: (message?: string) => void;
}
const Context = createContext<AuthContextValue | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const generation = useRef(0);
  const complete = useCallback((data: SessionData) => {
    generation.current += 1;
    setSessionContext(data.csrf_token, data.active_workspace_id || "");
    setSession(data);
    setLoading(false);
    setError("");
    setMessage("");
  }, []);
  const expire = useCallback(
    (reason = "La sesión ha terminado. Inicia sesión de nuevo.") => {
      generation.current += 1;
      clearSessionContext();
      setSession(null);
      setLoading(false);
      setMessage(reason);
    },
    [],
  );
  const refresh = useCallback(async () => {
    const started = generation.current;
    try {
      const data = await request<SessionData>("/auth/session");
      if (generation.current === started) complete(data);
    } catch (caught) {
      if (generation.current !== started) return;
      clearSessionContext();
      setSession(null);
      setLoading(false);
      if (!(
        caught instanceof Error &&
        "status" in caught &&
        caught.status === 401
      ))
        setError(
          caught instanceof Error
            ? caught.message
            : "No se pudo comprobar la sesión.",
        );
    }
  }, [complete]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  useEffect(() => {
    const handler = () => expire();
    window.addEventListener("blackbox:session-expired", handler);
    return () =>
      window.removeEventListener("blackbox:session-expired", handler);
  }, [expire]);
  const logout = async () => {
    await request("/auth/logout", { method: "POST" });
    expire("Has cerrado sesión.");
  };
  const select = async (id: string) => {
    await request("/auth/workspace", {
      method: "POST",
      body: JSON.stringify({ workspace_id: id }),
    });
    clearSessionContext();
    setSession(null);
    setLoading(true);
    await refresh();
  };
  const current = session?.workspaces.find(
    (w) => w.id === session.active_workspace_id,
  );
  return (
    <Context.Provider
      value={{
        session,
        loading,
        error,
        message,
        role: current?.role || "",
        workspaceId: current?.id || "",
        canWrite: !!current && current.role !== "viewer",
        refresh,
        complete,
        logout,
        select,
        expire,
      }}
    >
      {children}
    </Context.Provider>
  );
}
export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error("Falta el contexto de sesión.");
  return value;
}
