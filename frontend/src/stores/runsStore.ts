import { create } from "zustand";
import { mergeEvents, type RunDetail, type RunEvent, type RunSummary } from "@/lib/api/runs-contract";
import { runsService } from "@/services/runsService";
export type Connection = "idle" | "connecting" | "live" | "reconnecting" | "finished" | "error";
type RunState = {
    detail?: RunDetail;
    detailError?: string;
    events: RunEvent[];
    connection: Connection;
    streamError?: string;
};
type Store = {
    lists: Record<string, {
        data?: RunSummary[];
        error?: string;
        pending?: boolean;
    }>;
    runs: Record<string, RunState>;
    loadList: (projectId: string) => Promise<void>;
    loadDetail: (projectId: string, runId: string) => Promise<void>;
    // Opens the event stream; returns a cleanup that closes it.
    follow: (projectId: string, runId: string) => () => void;
};
const blank: RunState = { events: [], connection: "idle" };
const key = (projectId: string, runId: string) => `${projectId}:${runId}`;
const RETRY_MS = [1000, 2000, 4000, 8000];
export const useRunsStore = create<Store>((set, get) => {
    const patch = (k: string, next: Partial<RunState>) => set(s => ({ runs: { ...s.runs, [k]: { ...(s.runs[k] ?? blank), ...next } } }));
    return {
        lists: {},
        runs: {},
        loadList: async (projectId) => {
            if (get().lists[projectId]?.pending)
                return;
            set(s => ({ lists: { ...s.lists, [projectId]: { ...s.lists[projectId], pending: true, error: undefined } } }));
            try {
                const data = await runsService.list(projectId);
                set(s => ({ lists: { ...s.lists, [projectId]: { data: data.filter(r => r.project_id === projectId) } } }));
            }
            catch (e) {
                set(s => ({ lists: { ...s.lists, [projectId]: { ...s.lists[projectId], pending: false, error: e instanceof Error ? e.message : "Could not load runs." } } }));
            }
        },
        loadDetail: async (projectId, runId) => {
            const k = key(projectId, runId);
            try {
                patch(k, { detail: await runsService.detail(projectId, runId), detailError: undefined });
            }
            catch (e) {
                patch(k, { detailError: e instanceof Error ? e.message : "Could not load the run." });
            }
        },
        follow: (projectId, runId) => {
            const k = key(projectId, runId);
            const controller = new AbortController();
            let attempt = 0;
            const lastSeq = () => get().runs[k]?.events.at(-1)?.sequence ?? 0;
            const onEvent = (event: RunEvent) => {
                attempt = 0;
                const current = get().runs[k] ?? blank;
                patch(k, { events: mergeEvents(current.events, [event]), connection: "live" });
            };
            const loop = async () => {
                while (!controller.signal.aborted) {
                    patch(k, { connection: attempt === 0 ? (lastSeq() === 0 ? "connecting" : "live") : "reconnecting", streamError: undefined });
                    try {
                        const outcome = await runsService.stream(projectId, runId, lastSeq(), onEvent, controller.signal);
                        if (outcome === "finished") {
                            patch(k, { connection: "finished" });
                            void get().loadDetail(projectId, runId);
                            return;
                        }
                    }
                    catch (e) {
                        if (controller.signal.aborted)
                            return;
                        if (attempt >= RETRY_MS.length) {
                            patch(k, { connection: "error", streamError: e instanceof Error ? e.message : "The event stream failed." });
                            return;
                        }
                    }
                    if (controller.signal.aborted)
                        return;
                    patch(k, { connection: "reconnecting" });
                    await new Promise(r => setTimeout(r, RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)]));
                    attempt++;
                }
            };
            void loop();
            return () => controller.abort();
        },
    };
});
export const runKey = key;
