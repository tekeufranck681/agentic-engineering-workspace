// Delivery mirrors backend/app/modules/delivery/service.py `Delivery`.
export type Delivery = {
    run_id: string;
    task_id: string;
    branch: string;
    base_sha: string;
    commit_sha: string;
    changed_paths: string[];
    pr_number: number;
    pr_url: string;
    tests_passed: number;
    evidence: {
        kind: string;
        id: string;
    }[];
};
export type RunSummary = {
    id: string;
    project_id: string;
    task_id: string;
    attempt: number;
    status: string;
    error: string | null;
};
function object(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Invalid delivery response");
    return value as Record<string, unknown>;
}
function string(value: unknown): string { if (typeof value !== "string")
    throw new Error("Invalid text"); return value; }
function count(value: unknown): number { if (typeof value !== "number" || !Number.isInteger(value) || value < 0)
    throw new Error("Invalid count"); return value; }
function list(value: unknown): unknown[] { if (!Array.isArray(value))
    throw new Error("Invalid list"); return value; }
const runStatuses = ["queued", "running", "evaluating", "succeeded", "failed", "cancelled"];
// Only GitHub pull request URLs are rendered as links.
export function isPullRequestUrl(value: string) {
    try {
        const url = new URL(value);
        return url.protocol === "https:" && url.hostname === "github.com" && /^\/[^/]+\/[^/]+\/pull\/\d+\/?$/.test(url.pathname);
    }
    catch {
        return false;
    }
}
export function parseDelivery(value: unknown): Delivery {
    const d = object(value);
    const prUrl = string(d.pr_url);
    if (!isPullRequestUrl(prUrl))
        throw new Error("Invalid pull request URL");
    return { run_id: string(d.run_id), task_id: string(d.task_id), branch: string(d.branch), base_sha: string(d.base_sha), commit_sha: string(d.commit_sha), changed_paths: list(d.changed_paths).map(string), pr_number: count(d.pr_number), pr_url: prUrl, tests_passed: count(d.tests_passed), evidence: list(d.evidence).map(e => { const r = object(e); return { kind: string(r.kind), id: string(r.id) }; }) };
}
// The locked API surface names GET /projects/{id}/traceability; its body is
// accepted as either a list of deliveries or { deliveries: [...] }.
export function parseDeliveries(value: unknown): Delivery[] {
    return (Array.isArray(value) ? value : list(object(value).deliveries)).map(parseDelivery);
}
export function parseRuns(value: unknown): RunSummary[] {
    return (Array.isArray(value) ? value : list(object(value).runs)).map(v => {
        const r = object(v);
        const status = string(r.status);
        if (!runStatuses.includes(status))
            throw new Error("Invalid run status");
        return { id: string(r.id), project_id: string(r.project_id), task_id: string(r.task_id), attempt: count(r.attempt), status, error: r.error == null ? null : string(r.error) };
    });
}
