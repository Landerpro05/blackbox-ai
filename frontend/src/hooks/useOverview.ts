import { useCallback, useEffect, useState } from "react";
import { fetchOverview } from "../services/api";
import type { DashboardResponse, HealthResponse } from "../types/api";

type OverviewState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; health: HealthResponse; dashboard: DashboardResponse };

export function useOverview() {
  const [state, setState] = useState<OverviewState>({ status: "loading" });
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    fetchOverview(controller.signal)
      .then((result) => {
        if (!controller.signal.aborted)
          setState({ status: "ready", ...result });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            status: "error",
            message:
              error instanceof Error
                ? error.message
                : "No se pudo cargar el dashboard.",
          });
      });
    return () => controller.abort();
  }, [revision]);
  return { state, refresh };
}
