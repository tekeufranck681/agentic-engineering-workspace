import { apiRequest } from "@/lib/api/client";
import { parseCriteria, parseRequirements } from "@/lib/api/requirements-contract";
export const requirementsService = {
    criteria: (projectId: string, setId: string) => apiRequest(`/requirements/set/${encodeURIComponent(setId)}/acceptance-criteria?project_id=${encodeURIComponent(projectId)}`, parseCriteria),
    generateCriteria: (projectId: string, setId: string) => apiRequest(`/requirements/set/${encodeURIComponent(setId)}/acceptance-criteria`, parseCriteria, { method: "POST", body: { project_id: projectId }, timeoutMs: 310000 }),
    analyze: (projectId: string, brief: string) => apiRequest("/requirements/analyze", parseRequirements, { method: "POST", body: { project_id: projectId, brief }, timeoutMs: 130000 }),
    read: (projectId: string, id: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}?project_id=${encodeURIComponent(projectId)}`, parseRequirements),
    approve: (projectId: string, id: string, reviewer: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}/approve`, parseRequirements, { method: "POST", body: { approved_by: reviewer, project_id: projectId } }),
    lock: (projectId: string, id: string, reviewer: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}/lock`, parseRequirements, { method: "POST", body: { locked_by: reviewer, project_id: projectId } }),
};
