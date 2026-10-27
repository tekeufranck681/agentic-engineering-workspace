export type ValidationPlanSummary = {
    id: string;
    version: number;
    status: string;
    cases: { test_id: string; ac_id: string; title: string; checks: string[] }[];
};
function object(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Invalid validation plan");
    return value as Record<string, unknown>;
}
const str = (v: unknown) => { if (typeof v !== "string") throw new Error("Invalid text"); return v; };
// Accepts the backend ValidationPlan and the already-parsed summary.
export function parseValidationPlan(value: unknown): ValidationPlanSummary {
    const p = object(value);
    if (typeof p.version !== "number" || !Array.isArray(p.cases))
        throw new Error("Invalid validation plan");
    return { id: str(p.id), version: p.version, status: str(p.status), cases: p.cases.map(v => {
            const c = object(v);
            const checks = Array.isArray(c.checks) ? c.checks.map(x => typeof x === "string" ? x : str(object(x).target)) : [];
            return { test_id: str(c.test_id), ac_id: str(c.ac_id), title: str(c.title), checks };
        }) };
}
