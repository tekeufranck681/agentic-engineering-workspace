import { create } from "zustand";
import type { Delivery, RunSummary } from "@/lib/api/delivery-contract";
import { deliveryService } from "@/services/deliveryService";
type Slice<T> = {
    data?: T;
    error?: string;
};
type Entry = {
    pending?: boolean;
    deliveries: Slice<Delivery[]>;
    runs: Slice<RunSummary[]>;
};
type Store = {
    entries: Record<string, Entry>;
    load: (projectId: string) => Promise<void>;
};
const message = (e: unknown) => e instanceof Error ? e.message : "Request failed.";
function settle<T>(result: PromiseSettledResult<T>): Slice<T> {
    return result.status === "fulfilled" ? { data: result.value } : { error: message(result.reason) };
}
export const useDeliveryStore = create<Store>((set, get) => ({
    entries: {},
    load: async (projectId) => {
        const old = get().entries[projectId];
        if (old?.pending)
            return;
        set(s => ({ entries: { ...s.entries, [projectId]: { deliveries: old?.deliveries ?? {}, runs: old?.runs ?? {}, pending: true } } }));
        const [deliveries, runs] = await Promise.allSettled([deliveryService.deliveries(projectId), deliveryService.runs(projectId)]);
        const next: Entry = { deliveries: settle(deliveries), runs: settle(runs) };
        if (next.runs.data?.some(r => r.project_id !== projectId))
            next.runs = { error: "The response belongs to another project. No records were displayed." };
        set(s => ({ entries: { ...s.entries, [projectId]: next } }));
    },
}));
