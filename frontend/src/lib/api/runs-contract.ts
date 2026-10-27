import { parseRuns, type RunSummary } from "@/lib/api/delivery-contract";
import { parseTask, type PlanTask } from "@/lib/api/planning-contract";
export { parseRuns, type RunSummary };
export { mergeEvents, parseEvent, verdictsOf, type AcVerdict, type RunEvent } from "./run-events";
export type RunDetail = {
    run: RunSummary;
    task: PlanTask | null;
};
function object(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Invalid run response");
    return value as Record<string, unknown>;
}
export function parseRunDetail(value: unknown): RunDetail {
    const body = object(value);
    const [run] = parseRuns([body.run]);
    return { run, task: body.task == null ? null : parseTask(body.task) };
}
