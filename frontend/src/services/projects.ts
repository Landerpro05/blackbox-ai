import { request } from "./api";
import type { Project, ProjectInput, ProjectList } from "../types/api";

export const projectsApi = {
  list: (offset: number, signal?: AbortSignal) =>
    request<ProjectList>(`/projects?limit=12&offset=${offset}`, { signal }),
  get: (id: string, signal?: AbortSignal) =>
    request<Project>(`/projects/${encodeURIComponent(id)}`, { signal }),
  create: (data: ProjectInput) =>
    request<Project>("/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: Partial<ProjectInput>) =>
    request<Project>(`/projects/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    request<void>(`/projects/${encodeURIComponent(id)}`, { method: "DELETE" }),
};
