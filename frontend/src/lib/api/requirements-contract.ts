export type Requirement = {
    id: string;
    project_id: string;
    title: string;
    description: string;
    version: number;
    status: string;
    priority: string;
    type: string;
    trace: {
        ac_ids: string[];
    };
};
export type RequirementsResult = {
    set: {
        id: string;
        project_id: string;
        version: number;
        status: string;
        summary: string;
        assumptions: string[];
        open_questions: string[];
    };
    requirements: Requirement[];
};
function object(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Invalid requirements response");
    return value as Record<string, unknown>;
}
function string(value: unknown): string { if (typeof value !== "string")
    throw new Error("Invalid text"); return value; }
function strings(value: unknown): string[] { if (!Array.isArray(value))
    throw new Error("Invalid list"); return value.map(string); }
function version(value: unknown): number { if (typeof value !== "number" || !Number.isInteger(value) || value < 1)
    throw new Error("Invalid version"); return value; }
export function parseRequirements(value: unknown): RequirementsResult {
    const body = object(value), set = object(body.set);
    if (!Array.isArray(body.requirements))
        throw new Error("Invalid requirements");
    return { set: { id: string(set.id), project_id: string(set.project_id), version: version(set.version), status: string(set.status), summary: string(set.summary), assumptions: strings(set.assumptions), open_questions: strings(set.open_questions) }, requirements: body.requirements.map(value => {
            const r = object(value), trace = object(r.trace);
            return { id: string(r.id), project_id: string(r.project_id), title: string(r.title), description: string(r.description), version: version(r.version), status: string(r.status), priority: string(r.priority), type: string(r.type), trace: { ac_ids: strings(trace.ac_ids) } };
        }) };
}
export type Criterion = {
    id: string;
    requirement_id: string;
    title: string;
    given: string[];
    when: string[];
    then: string[];
    verification: string;
};
// Accepts the backend AcceptanceCriterion and the already-parsed shape.
export function parseCriteria(value: unknown): Criterion[] {
    const body = object(value);
    if (!Array.isArray(body.acceptance_criteria))
        throw new Error("Invalid acceptance criteria");
    return body.acceptance_criteria.map(v => {
        const a = object(v);
        const verification = a.verification && typeof a.verification === "object" ? string((a.verification as Record<string, unknown>).kind) : typeof a.verification === "string" ? a.verification : "";
        return { id: string(a.id), requirement_id: string(a.requirement_id), title: string(a.title), given: strings(a.given), when: strings(a.when), then: strings(a.then), verification };
    });
}
