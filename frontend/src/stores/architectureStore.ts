import { create } from "zustand";
import { ApiError } from "@/lib/api/client";
import type { ArchitectureResult } from "@/lib/api/architecture-contract";
import { architectureService } from "@/services/architectureService";
type Entry = {
    data?: ArchitectureResult;
    pending?: "generate" | "read";
    error?: string;
    uncertain?: boolean;
};
type Store = {
    entries: Record<string, Entry>;
    generate: (projectId: string, requirementsSetId: string, context: string) => Promise<void>;
    read: (projectId: string, architectureId: string) => Promise<void>;
};
export const useArchitectureStore = create<Store>((set, get) => {
    async function run(projectId: string, command: "generate" | "read", request: () => Promise<ArchitectureResult>) {
        const old = get().entries[projectId] ?? {};
        if (old.pending || (old.uncertain && command !== "read"))
            return;
        set(s => ({ entries: { ...s.entries, [projectId]: { ...old, pending: command, error: undefined } } }));
        try {
            const data = await request();
            if (data.architecture.project_id !== projectId || data.decisions.some(d => d.project_id !== projectId) || data.contracts.some(c => c.project_id !== projectId))
                throw new ApiError(502, "The response belongs to another project. No records were displayed.", command === "generate");
            set(s => ({ entries: { ...s.entries, [projectId]: { data } } }));
        }
        catch (e) {
            const error = e instanceof Error ? e.message : "Architecture request failed.";
            set(s => ({ entries: { ...s.entries, [projectId]: { ...old, error, uncertain: (e instanceof ApiError && e.uncertain) || (command === "read" && old.uncertain), pending: undefined } } }));
        }
    }
    return {
        entries: {},
        generate: (projectId, requirementsSetId, context) => run(projectId, "generate", () => architectureService.generate(projectId, requirementsSetId, context)),
        read: (projectId, architectureId) => run(projectId, "read", () => architectureService.read(architectureId)),
    };
});
