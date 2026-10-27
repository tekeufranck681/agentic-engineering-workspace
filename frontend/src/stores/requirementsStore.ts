import { create } from "zustand";
import { rememberArtifact } from "@/lib/recent-artifacts";
import { ApiError } from "@/lib/api/client";
import type { RequirementsResult } from "@/lib/api/requirements-contract";
import { requirementsService } from "@/services/requirementsService";
type Entry = {
    data?: RequirementsResult;
    pending?: string;
    error?: string;
    uncertain?: boolean;
};
type Store = {
    entries: Record<string, Entry>;
    execute: (projectId: string, command: "analyze" | "read" | "approve" | "lock", value: string, reviewer?: string) => Promise<void>;
};
export const useRequirementsStore = create<Store>((set, get) => ({
    entries: {},
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
