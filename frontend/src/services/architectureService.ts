import { apiRequest } from "@/lib/api/client";
import { parseArchitecture } from "@/lib/api/architecture-contract";
export const architectureService = {
    generate: (projectId: string, requirementsSetId: string, context: string) => apiRequest("/architecture/generate", parseArchitecture, { method: "POST", body: { project_id: projectId, requirements_set_id: requirementsSetId, context }, timeoutMs: 190000 }),
    accept: (projectId: string, id: string, reviewer: string) => apiRequest(`/architecture/${encodeURIComponent(id)}/accept`, parseArchitecture, { method: "POST", body: { project_id: projectId, accepted_by: reviewer } }),
    read: (projectId: string, id: string) => apiRequest(`/architecture/${encodeURIComponent(id)}?project_id=${encodeURIComponent(projectId)}`, parseArchitecture),
};
