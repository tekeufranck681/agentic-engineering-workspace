import { parsePlan, parseReadiness } from "@/lib/api/planning-contract";
export const dynamic = "force-dynamic";
const projectPattern = /^[0-9a-f-]{36}$/i;
async function proxy(request: Request, context: {
    params: Promise<{
        segments: string[];
    }>;
}) {
    const { segments } = await context.params;
    const path = segments.join("/");
    const projectId = new URL(request.url).searchParams.get("project_id") ?? "";
    const read = request.method === "GET" && /^ARCH-\d+$/.test(path);
    const decompose = request.method === "POST" && path === "decompose";
    const readiness = request.method === "POST" && /^tasks\/TASK-\d+\/readiness$/.test(path);
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number, uncertain = false) => Response.json({ message, uncertain }, { status, headers });
    if (!read && !decompose && !readiness)
        return fail("Unsupported planning action.", 400);
    if (read && !projectPattern.test(projectId))
        return fail("A valid project is required to load a plan.", 422);
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Planning service is not configured. Contact the workspace operator.", 503);
    let body;
    if (!read) {
        try {
            const input = await request.json();
            if (typeof input.project_id !== "string" || !projectPattern.test(input.project_id))
                return fail("A valid project is required.", 422);
            if (decompose) {
                if (typeof input.architecture_id !== "string" || !/^ARCH-\d+$/.test(input.architecture_id))
                    return fail("Enter an architecture ID such as ARCH-001.", 422);
                if (typeof input.requirements_set_id !== "string" || (input.requirements_set_id && !/^RSET-\d+$/.test(input.requirements_set_id)))
                    return fail("Requirements set ID must look like RSET-001.", 422);
                if (typeof input.context !== "string" || input.context.length > 20000)
                    return fail("Planning context must be at most 20,000 characters.", 422);
                body = { project_id: input.project_id, architecture_id: input.architecture_id, requirements_set_id: input.requirements_set_id, context: input.context };
            }
            else
                body = { project_id: input.project_id };
        }
        catch {
            return fail("Invalid request body.", 400);
        }
    }
    let sent = false;
    try {
        const url = new URL(base.replace(/\/$/, "") + "/planning/" + path);
        if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
            return fail("Planning service URL is invalid.", 503);
        if (read)
            url.searchParams.set("project_id", projectId);
        sent = true;
        const response = await fetch(url, { method: request.method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(decompose ? 180000 : 8000) });
        if (!response.ok) {
            const messages: Record<number, string> = { 404: "This plan or task was not found for the project. Confirm the ID or contact the backend owner.", 409: "The task status changed. Reload the plan.", 422: "Planning was rejected. The architecture must exist for this project.", 503: "The model runtime or planning service is unavailable. Contact the workspace operator." };
            return fail(messages[response.status] ?? "Planning service failed. Reload the plan before retrying.", response.status >= 500 ? 502 : response.status, decompose && response.status >= 500);
        }
        const upstream = await response.json();
        return Response.json(readiness ? parseReadiness(upstream) : parsePlan(upstream), { headers });
    }
    catch {
        return fail(decompose ? "Task creation could not be confirmed. Load the plan before decomposing again." : "Could not reach the planning service. Try again.", 502, decompose && sent);
    }
}
export { proxy as GET, proxy as POST };
