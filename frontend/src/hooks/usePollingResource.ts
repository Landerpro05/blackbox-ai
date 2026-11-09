import { useEffect, useState } from "react";
import { ApiError } from "../services/api";

type State<T> =
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "error"; message: string; code?: number };

export function usePollingResource<T>(
  load: (signal: AbortSignal) => Promise<T>,
  shouldPoll: (data: T) => boolean,
) {
  const [state, setState] = useState<State<T>>({ status: "loading" });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    setState({ status: "loading" });
    const read = async () => {
      try {
        const data = await load(controller.signal);
        if (controller.signal.aborted) return;
        setState({ status: "ready", data });
        if (shouldPoll(data)) timer = setTimeout(read, 1500);
      } catch (error) {
        if (!controller.signal.aborted)
          setState({
            status: "error",
            message:
              error instanceof Error
                ? error.message
                : "No se pudo consultar el análisis.",
            code: error instanceof ApiError ? error.status : undefined,
          });
      }
    };
    void read();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, shouldPoll, revision]);
  return { state, reload: () => setRevision((value) => value + 1) };
}
