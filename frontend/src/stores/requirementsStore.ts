import { create } from "zustand";
import { recallArtifact, rememberArtifact } from "@/lib/recent-artifacts";
import type { ValidationPlanSummary } from "@/lib/api/validation-contract";
import { ApiError } from "@/lib/api/client";
import type { Criterion, RequirementsResult } from "@/lib/api/requirements-contract";
import { requirementsService } from "@/services/requirementsService";
type Entry = {
    data?: RequirementsResult;
    pending?: string;
    error?: string;
    uncertain?: boolean;
};
type CriteriaEntry = {
    data?: Criterion[];
    pending?: "load" | "generate";
    error?: string;
};
type Store = {
    entries: Record<string, Entry>;
    criteria: Record<string, CriteriaEntry>;
    plans: Record<string, { data?: ValidationPlanSummary; pending?: "generate" | "approve" | "load"; error?: string }>;
    planAction: (projectId: string, action: "generate" | "approve" | "load", setId: string) => Promise<void>;
    loadCriteria: (projectId: string, setId: string, generate?: boolean) => Promise<void>;
    execute: (projectId: string, command: "analyze" | "read" | "approve" | "lock", value: string, reviewer?: string) => Promise<void>;
};
export const useRequirementsStore = create<Store>((set, get) => ({
    entries: {},
    criteria: {},
    plans: {},
    planAction: async (projectId, action, setId) => {
        const old = get().plans[projectId] ?? {};
        if (old.pending)
            return;
        const planId = old.data?.id ?? recallArtifact(projectId, "vplan");
        if (action !== "generate" && !planId)
            return;
        set(s => ({ plans: { ...s.plans, [projectId]: { ...old, pending: action, error: undefined } } }));
        try {
            const data = action === "generate" ? await requirementsService.generatePlan(projectId, setId) : action === "approve" ? await requirementsService.approvePlan(projectId, planId!) : await requirementsService.readPlan(projectId, planId!);
            rememberArtifact(projectId, "vplan", data.id);
            set(s => ({ plans: { ...s.plans, [projectId]: { data } } }));
        }
        catch (e) {
            set(s => ({ plans: { ...s.plans, [projectId]: { ...old, pending: undefined, error: e instanceof Error ? e.message : "Validation plan request failed." } } }));
        }
    },
    loadCriteria: async (projectId, setId, generate = false) => {
        const old = get().criteria[projectId] ?? {};
        if (old.pending)
            return;
        set(s => ({ criteria: { ...s.criteria, [projectId]: { ...old, pending: generate ? "generate" : "load", error: undefined } } }));
        try {
            const data = generate ? await requirementsService.generateCriteria(projectId, setId) : await requirementsService.criteria(projectId, setId);
            const merged = generate ? [...(old.data ?? []), ...data] : data;
            set(s => ({ criteria: { ...s.criteria, [projectId]: { data: merged } } }));
        }
        catch (e) {
            set(s => ({ criteria: { ...s.criteria, [projectId]: { ...old, pending: undefined, error: e instanceof Error ? e.message : "Acceptance criteria request failed." } } }));
        }
    },
    execute: async (projectId, command, value, reviewer = "") => {
        const old = get().entries[projectId] ?? {};
        if (old.pending || (old.uncertain && command !== "read"))
            return;
        set(s => ({ entries: { ...s.entries, [projectId]: { ...old, pending: command, error: undefined } } }));
        try {
            const data = command === "analyze" ? await requirementsService.analyze(projectId, value) : command === "read" ? await requirementsService.read(projectId, value) : command === "approve" ? await requirementsService.approve(projectId, value, reviewer) : await requirementsService.lock(projectId, value, reviewer);
            if (data.set.project_id !== projectId || data.requirements.some(r => r.project_id !== projectId))
                throw new ApiError(502, "The response belongs to another project. No records were displayed.", command !== "read");
            rememberArtifact(projectId, "rset", data.set.id);
            set(s => ({ entries: { ...s.entries, [projectId]: { data } } }));
        }
        catch (e) {
            const error = e instanceof Error ? e.message : "Requirements request failed.";
            set(s => ({ entries: { ...s.entries, [projectId]: { ...old, error, uncertain: (e instanceof ApiError && e.uncertain) || (command === "read" && old.uncertain), pending: undefined } } }));
        }
    }
}));
