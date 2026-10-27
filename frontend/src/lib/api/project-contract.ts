// Mirrors ProjectRead in backend/app/modules/persistence/schemas.py.
export interface Project {
  id: string;
  name: string;
  description: string | null;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}
export const isProjectId = (value: string) =>
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
export function parseProject(value: unknown): Project {
  if (typeof value !== "object" || value === null)
    throw new Error("Invalid project response");
  const project = value as Record<string, unknown>;
  if (
    typeof project.id !== "string" ||
    !isProjectId(project.id) ||
    typeof project.name !== "string" ||
    !project.name.trim() ||
    (project.description !== null && typeof project.description !== "string") ||
    (project.status !== "active" && project.status !== "archived") ||
    typeof project.created_at !== "string" ||
    !Number.isFinite(Date.parse(project.created_at)) ||
    typeof project.updated_at !== "string" ||
    !Number.isFinite(Date.parse(project.updated_at))
  )
    throw new Error("Invalid project response");
  return {
    id: project.id,
    name: project.name,
    description: project.description,
    status: project.status,
    created_at: project.created_at,
    updated_at: project.updated_at,
  };
}
export function parseProjects(value: unknown): Project[] {
  if (!Array.isArray(value)) throw new Error("Invalid projects response");
  return value.map(parseProject);
}
