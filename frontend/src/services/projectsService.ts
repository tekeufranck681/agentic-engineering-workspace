import { apiRequest } from "@/lib/api/client";
import {
  parseProject,
  parseProjects,
  parseProjectCreate,
  parseBinding,
  parseBindingCreate,
  type ProjectCreate,
  type RepositoryBindingCreate,
} from "@/lib/api/project-contract";
export const projectsService = {
  list: (offset = 0) => apiRequest(`/projects?offset=${offset}`, parseProjects),
  get: (id: string) =>
    apiRequest(`/projects/${encodeURIComponent(id)}`, parseProject),
  create: (input: ProjectCreate) =>
    apiRequest("/projects", parseProject, {
      method: "POST",
      body: parseProjectCreate(input),
    }),
  getBinding: (id: string) =>
    apiRequest(
      `/projects/${encodeURIComponent(id)}/repository-binding`,
      (value) => (value === null ? null : parseBinding(value)),
    ),
  bind: (id: string, input: RepositoryBindingCreate) =>
    apiRequest(
      `/projects/${encodeURIComponent(id)}/repository-binding`,
      parseBinding,
      { method: "POST", body: parseBindingCreate(input) },
    ),
};
