import { apiRequest } from "@/lib/api/client";
import { parsePlan, parseReadiness } from "@/lib/api/planning-contract";
export const planningService = {
    decompose: (projectId: string, architectureId: string, requirementsSetId: string, context: string) => apiRequest("/planning/decompose", parsePlan, { method: "POST", body: { project_id: projectId, architecture_id: architectureId, requirements_set_id: requirementsSetId, context }, timeoutMs: 190000 }),
    read: (projectId: string, architectureId: string) => apiRequest(`/planning/${encodeURIComponent(architectureId)}?project_id=${encodeURIComponent(projectId)}`, parsePlan),
    // Readiness is a computed read; it is not a user-visible write.
    readiness: (projectId: string, taskId: string) => apiRequest(`/planning/tasks/${encodeURIComponent(taskId)}/readiness`, parseReadiness, { method: "POST", body: { project_id: projectId } }),
};
