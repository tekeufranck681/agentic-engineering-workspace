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

export interface ProjectCreate {
  name: string;
  description: string | null;
}
export function parseProjectCreate(value: unknown): ProjectCreate {
  if (typeof value !== "object" || value === null)
    throw new Error("Enter a project name.");
  const row = value as Record<string, unknown>;
  if (
    typeof row.name !== "string" ||
    !row.name.trim() ||
    row.name.trim().length > 200
  )
    throw new Error("Project name must contain 1 to 200 characters.");
  if (
    row.description !== null &&
    row.description !== undefined &&
    (typeof row.description !== "string" || row.description.length > 5000)
  )
    throw new Error("Description must contain at most 5,000 characters.");
  return {
    name: row.name.trim(),
    description:
      typeof row.description === "string"
        ? row.description.trim() || null
        : null,
  };
}
export interface RepositoryBindingCreate {
  provider: "github";
  owner: string;
  name: string;
  default_branch: string;
  base_sha: string | null;
  html_url: string;
}
export interface RepositoryBinding extends Omit<
  RepositoryBindingCreate,
  "html_url"
> {
  id: string;
  project_id: string;
  full_name: string;
  html_url: string | null;
  status: "active" | "disconnected";
  bound_at: string;
}
export function parseBindingCreate(value: unknown): RepositoryBindingCreate {
  if (typeof value !== "object" || value === null)
    throw new Error("Enter repository details.");
  const row = value as Record<string, unknown>;
  if (
    row.provider !== "github" ||
    typeof row.owner !== "string" ||
    !/^[a-z\d](?:[a-z\d-]{0,37}[a-z\d])?$/i.test(row.owner) ||
    typeof row.name !== "string" ||
    !/^[a-z\d_.-]{1,100}$/i.test(row.name) ||
    row.name === "." ||
    row.name === ".."
  )
    throw new Error("Enter a valid GitHub owner and repository name.");
  if (
    typeof row.default_branch !== "string" ||
    !row.default_branch.trim() ||
    row.default_branch.length > 200 ||
    /\s/.test(row.default_branch)
  )
    throw new Error(
      "Enter a branch name without spaces, up to 200 characters.",
    );
  if (
    row.base_sha !== null &&
    row.base_sha !== undefined &&
    (typeof row.base_sha !== "string" || !/^[a-f\d]{7,40}$/i.test(row.base_sha))
  )
    throw new Error(
      "Base commit must be a hexadecimal SHA of 7 to 40 characters.",
    );
  return {
    provider: "github",
    owner: row.owner,
    name: row.name,
    default_branch: row.default_branch,
    base_sha: typeof row.base_sha === "string" ? row.base_sha : null,
    html_url: `https://github.com/${row.owner}/${row.name}`,
  };
}
export function bindingFromUrl(
  url: string,
  branch: string,
  sha: string,
): RepositoryBindingCreate {
  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    throw new Error(
      "Enter a GitHub URL such as https://github.com/owner/repository.",
    );
  }
  const parts = parsed.pathname.replace(/\/$/, "").split("/").filter(Boolean);
  if (
    parsed.protocol !== "https:" ||
    parsed.hostname !== "github.com" ||
    parsed.port ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    parts.length !== 2
  )
    throw new Error(
      "Use the HTTPS GitHub repository URL without credentials or extra paths.",
    );
  return parseBindingCreate({
    provider: "github",
    owner: parts[0],
    name: parts[1].replace(/\.git$/, ""),
    default_branch: branch.trim(),
    base_sha: sha.trim() || null,
  });
}
export function parseBinding(value: unknown): RepositoryBinding {
  if (typeof value !== "object" || value === null)
    throw new Error("Invalid repository binding response");
  const row = value as Record<string, unknown>;
  const data = parseBindingCreate(row);
  if (
    typeof row.id !== "string" ||
    !isProjectId(row.id) ||
    typeof row.project_id !== "string" ||
    !isProjectId(row.project_id) ||
    row.full_name !== `${data.owner}/${data.name}` ||
    (row.status !== "active" && row.status !== "disconnected") ||
    typeof row.bound_at !== "string" ||
    !Number.isFinite(Date.parse(row.bound_at))
  )
    throw new Error("Invalid repository binding response");
  return {
    ...data,
    id: row.id,
    project_id: row.project_id,
    full_name: row.full_name,
    status: row.status,
    bound_at: row.bound_at,
  };
}
