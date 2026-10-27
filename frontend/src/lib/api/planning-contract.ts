export type PlanTask = {
    id: string;
    project_id: string;
    version: number;
    status: string;
    title: string;
    description: string;
    target_paths: string[];
    size: string;
    depends_on: string[];
    readiness: string | null;
    blocking_reasons: string[];
    requirement_ids: string[];
    ac_ids: string[];
};
export type TaskDependency = {
    task_id: string;
    depends_on_id: string;
};
export type PlanResult = {
    tasks: PlanTask[];
    dependencies: TaskDependency[];
};
export type ReadinessResult = {
    task_id: string;
    readiness: "ready" | "blocked";
    blocking_reasons: string[];
};
function object(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Invalid planning response");
    return value as Record<string, unknown>;
}
function string(value: unknown): string { if (typeof value !== "string")
    throw new Error("Invalid text"); return value; }
function strings(value: unknown): string[] { if (value === undefined)
    return []; if (!Array.isArray(value))
    throw new Error("Invalid list"); return value.map(string); }
function version(value: unknown): number { if (typeof value !== "number" || !Number.isInteger(value) || value < 1)
    throw new Error("Invalid version"); return value; }
const statuses = ["pending", "ready", "running", "done", "failed", "cancelled"];
// Accepts both the backend Task shape (trace.*) and the already-parsed shape,
// because the proxy and the client both parse.
export function parseTask(value: unknown): PlanTask {
    const t = object(value);
    const trace = t.trace === undefined ? t : object(t.trace);
    const status = string(t.status);
    if (!statuses.includes(status))
        throw new Error("Invalid task status");
    if (t.readiness !== undefined && t.readiness !== null && t.readiness !== "ready" && t.readiness !== "blocked")
        throw new Error("Invalid readiness");
    return { id: string(t.id), project_id: string(t.project_id), version: version(t.version), status, title: string(t.title), description: string(t.description), target_paths: strings(t.target_paths), size: string(t.size), depends_on: strings(t.depends_on), readiness: (t.readiness as string | null | undefined) ?? null, blocking_reasons: strings(t.blocking_reasons), requirement_ids: strings(trace.requirement_ids), ac_ids: strings(trace.ac_ids) };
}
export function parsePlan(value: unknown): PlanResult {
    const body = object(value);
    if (!Array.isArray(body.tasks))
        throw new Error("Invalid tasks");
    const tasks = body.tasks.map(parseTask);
    const dependencies = body.dependencies === undefined
        ? tasks.flatMap(t => t.depends_on.map(d => ({ task_id: t.id, depends_on_id: d })))
        : (Array.isArray(body.dependencies) ? body.dependencies : []).map(value => { const d = object(value); return { task_id: string(d.task_id), depends_on_id: string(d.depends_on_id) }; });
    return { tasks, dependencies };
}
export function parseReadiness(value: unknown): ReadinessResult {
    const body = object(value);
    if (body.readiness !== "ready" && body.readiness !== "blocked")
        throw new Error("Invalid readiness");
    return { task_id: string(body.task_id), readiness: body.readiness, blocking_reasons: strings(body.blocking_reasons) };
}
