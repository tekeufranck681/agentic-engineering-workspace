import { apiRequest } from "@/lib/api/client";
import { parseCriteria, parseRequirements } from "@/lib/api/requirements-contract";
import { parseValidationPlan } from "@/lib/api/validation-contract";
export const requirementsService = {
    generatePlan: (projectId: string, setId: string) => apiRequest("/validation/generate", parseValidationPlan, { method: "POST", body: { project_id: projectId, requirements_set_id: setId }, timeoutMs: 310000 }),
    approvePlan: (projectId: string, planId: string) => apiRequest(`/validation/${encodeURIComponent(planId)}/approve`, parseValidationPlan, { method: "POST", body: { project_id: projectId } }),
    readPlan: (projectId: string, planId: string) => apiRequest(`/validation/${encodeURIComponent(planId)}?project_id=${encodeURIComponent(projectId)}`, parseValidationPlan),
    criteria: (projectId: string, setId: string) => apiRequest(`/requirements/set/${encodeURIComponent(setId)}/acceptance-criteria?project_id=${encodeURIComponent(projectId)}`, parseCriteria),
    generateCriteria: (projectId: string, setId: string) => apiRequest(`/requirements/set/${encodeURIComponent(setId)}/acceptance-criteria`, parseCriteria, { method: "POST", body: { project_id: projectId }, timeoutMs: 310000 }),
    analyze: (projectId: string, brief: string) => apiRequest("/requirements/analyze", parseRequirements, { method: "POST", body: { project_id: projectId, brief }, timeoutMs: 130000 }),
    read: (projectId: string, id: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}?project_id=${encodeURIComponent(projectId)}`, parseRequirements),
    approve: (projectId: string, id: string, reviewer: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}/approve`, parseRequirements, { method: "POST", body: { approved_by: reviewer, project_id: projectId } }),
    lock: (projectId: string, id: string, reviewer: string) => apiRequest(`/requirements/set/${encodeURIComponent(id)}/lock`, parseRequirements, { method: "POST", body: { locked_by: reviewer, project_id: projectId } }),
};
