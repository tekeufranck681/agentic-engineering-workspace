import { create } from "zustand";
import { ApiError } from "@/lib/api/client";
import type { PlanResult, ReadinessResult } from "@/lib/api/planning-contract";
import { planningService } from "@/services/planningService";
type Readiness = ReadinessResult & {
    pending?: boolean;
    error?: string;
};
type Entry = {
    data?: PlanResult;
    pending?: "decompose" | "read";
    error?: string;
    uncertain?: boolean;
    readiness: Record<string, Readiness>;
};
type Store = {
    entries: Record<string, Entry>;
    decompose: (projectId: string, architectureId: string, requirementsSetId: string, context: string) => Promise<void>;
    read: (projectId: string, architectureId: string) => Promise<void>;
    checkReadiness: (projectId: string, taskId: string) => Promise<void>;
};
const empty: Entry = { readiness: {} };
export const usePlanningStore = create<Store>((set, get) => {
    const patch = (projectId: string, next: Partial<Entry>) => set(s => ({ entries: { ...s.entries, [projectId]: { ...(s.entries[projectId] ?? empty), ...next } } }));
    async function run(projectId: string, command: "decompose" | "read", request: () => Promise<PlanResult>) {
        const old = get().entries[projectId] ?? empty;
        if (old.pending || (old.uncertain && command !== "read"))
            return;
        patch(projectId, { pending: command, error: undefined });
        try {
            const data = await request();
            if (data.tasks.some(t => t.project_id !== projectId))
                throw new ApiError(502, "The response belongs to another project. No records were displayed.", command === "decompose");
            set(s => ({ entries: { ...s.entries, [projectId]: { data, readiness: {} } } }));
        }
        catch (e) {
            const error = e instanceof Error ? e.message : "Planning request failed.";
            patch(projectId, { error, uncertain: (e instanceof ApiError && e.uncertain) || (command === "read" && old.uncertain), pending: undefined });
        }
    }
    return {
        entries: {},
        decompose: (projectId, architectureId, requirementsSetId, context) => run(projectId, "decompose", () => planningService.decompose(projectId, architectureId, requirementsSetId, context)),
        read: (projectId, architectureId) => run(projectId, "read", () => planningService.read(projectId, architectureId)),
        checkReadiness: async (projectId, taskId) => {
            if (get().entries[projectId]?.readiness[taskId]?.pending)
                return;
            const setReadiness = (value: Readiness) => set(s => { const e = s.entries[projectId] ?? empty; return { entries: { ...s.entries, [projectId]: { ...e, readiness: { ...e.readiness, [taskId]: value } } } }; });
            setReadiness({ task_id: taskId, readiness: "blocked", blocking_reasons: [], pending: true });
            try {
                setReadiness(await planningService.readiness(projectId, taskId));
            }
            catch (e) {
                setReadiness({ task_id: taskId, readiness: "blocked", blocking_reasons: [], error: e instanceof Error ? e.message : "Readiness check failed." });
            }
        },
    };
});
