import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../services/api";

type ResourceState<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string; code?: number };

/** The loader must have stable identity (useCallback when it uses route state). */
export function useResource<T>(loader: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<ResourceState<T>>({ status: "loading" });
  const [revision, setRevision] = useState(0);
  const reload = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    setState({ status: "loading" });
    loader(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setState({ status: "ready", data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted)
          setState({
            status: "error",
            message:
              error instanceof Error
                ? error.message
                : "No se pudieron cargar los datos.",
            code: error instanceof ApiError ? error.status : undefined,
          });
      });
    return () => controller.abort();
  }, [loader, revision]);
  return { state, reload };
}
