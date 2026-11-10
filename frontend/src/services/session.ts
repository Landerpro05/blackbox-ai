export const MIN_PASSWORD_LENGTH = 15;
export interface WorkspaceIdentity {
  id: string;
  name: string;
  role: "owner" | "admin" | "member" | "viewer";
}
export interface SessionData {
  user: { id: string; email: string };
  active_workspace_id: string | null;
  expires_at: string;
  csrf_token: string;
  workspaces: WorkspaceIdentity[];
}
let workspace = "";
let csrf = "";
let controller = new AbortController();
export function setSessionContext(token: string, id: string) {
  if (workspace !== id) {
    controller.abort();
    controller = new AbortController();
  }
  workspace = id;
  csrf = token;
}
export function clearSessionContext() {
  controller.abort();
  controller = new AbortController();
  workspace = "";
  csrf = "";
}
export function sessionHeaders() {
  return {
    "X-Blackbox-Request": "1",
    ...(workspace ? { "X-Workspace-ID": workspace } : {}),
    ...(csrf ? { "X-CSRF-Token": csrf } : {}),
  };
}
export const workspaceSignal = () => controller.signal;
export const workspaceQuery = () =>
  workspace ? `workspace=${encodeURIComponent(workspace)}` : "";
