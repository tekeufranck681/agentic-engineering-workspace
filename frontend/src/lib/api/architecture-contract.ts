export type ArchitectureComponent = {
    name: string;
    responsibility: string;
    depends_on: string[];
    requirement_ids: string[];
};
export type ArchitectureDecision = {
    id: string;
    project_id: string;
    version: number;
    status: string;
    title: string;
    context: string;
    decision: string;
    alternatives: string[];
    consequences: string[];
};
export type EngineeringContract = {
    id: string;
    project_id: string;
    version: number;
    status: string;
    kind: string;
    summary: string;
};
export type ArchitectureResult = {
    architecture: {
        id: string;
        project_id: string;
        version: number;
        status: string;
        summary: string;
        components: ArchitectureComponent[];
        decision_ids: string[];
        derived_from: string[];
    };
    decisions: ArchitectureDecision[];
    contracts: EngineeringContract[];
};
function object(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== "object" || Array.isArray(value))
        throw new Error("Invalid architecture response");
    return value as Record<string, unknown>;
}
function string(value: unknown): string { if (typeof value !== "string")
    throw new Error("Invalid text"); return value; }
function strings(value: unknown): string[] { if (!Array.isArray(value))
    throw new Error("Invalid list"); return value.map(string); }
function optionalStrings(value: unknown): string[] { return value === undefined ? [] : strings(value); }
function version(value: unknown): number { if (typeof value !== "number" || !Number.isInteger(value) || value < 1)
    throw new Error("Invalid version"); return value; }
function list(value: unknown): unknown[] { if (value === undefined)
    return []; if (!Array.isArray(value))
    throw new Error("Invalid list"); return value; }
function contractSummary(content: Record<string, unknown>): string {
    if (content.kind === "api")
        return `${list(content.endpoints).length} API endpoint(s)`;
    if (content.kind === "db_schema")
        return `${list(content.tables).length} database table(s)`;
    if (content.kind === "uml")
        return `UML ${string(content.diagram_type)} diagram`;
    throw new Error("Invalid contract kind");
}
export function parseContract(value: unknown): EngineeringContract {
    const c = object(value);
    const base = { id: string(c.id), project_id: string(c.project_id), version: version(c.version), status: string(c.status) };
    if (c.content === undefined)
        return { ...base, kind: string(c.kind), summary: string(c.summary) };
    const content = object(c.content);
    return { ...base, kind: string(content.kind), summary: contractSummary(content) };
}
export function parseArchitecture(value: unknown): ArchitectureResult {
    const body = object(value), doc = object(body.architecture);
    if (!Array.isArray(doc.components) || !Array.isArray(body.decisions))
        throw new Error("Invalid architecture");
    const components = doc.components.map(value => {
        const c = object(value);
        return { name: string(c.name), responsibility: string(c.responsibility), depends_on: optionalStrings(c.depends_on), requirement_ids: optionalStrings(c.requirement_ids) };
    });
    return {
        architecture: { id: string(doc.id), project_id: string(doc.project_id), version: version(doc.version), status: string(doc.status), summary: string(doc.summary), components, decision_ids: optionalStrings(doc.decision_ids), derived_from: list(doc.derived_from).map(ref => typeof ref === "string" ? ref : string(object(ref).id)) },
        decisions: body.decisions.map(value => {
            const d = object(value);
            return { id: string(d.id), project_id: string(d.project_id), version: version(d.version), status: string(d.status), title: string(d.title), context: string(d.context), decision: string(d.decision), alternatives: optionalStrings(d.alternatives), consequences: optionalStrings(d.consequences) };
        }),
        contracts: list(body.contracts).map(parseContract),
    };
}
