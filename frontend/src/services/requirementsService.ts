import { apiRequest } from "@/lib/api/client";
import { parseRequirements } from "@/lib/api/requirements-contract";
export const requirementsService = {
    analyze: (projectId: string, brief: string) => apiRequest("/requirements/analyze", parseRequirements, { method: "POST", body: { project_id: projectId, brief }, timeoutMs: 130000 }),
    read: (id: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}`, parseRequirements),
    approve: (id: string, reviewer: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}/approve`, parseRequirements, { method: "POST", body: { approved_by: reviewer } }),
    lock: (id: string, reviewer: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}/lock`, parseRequirements, { method: "POST", body: { locked_by: reviewer } }),
};
