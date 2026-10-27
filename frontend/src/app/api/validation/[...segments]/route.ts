import { parseValidationPlan } from "@/lib/api/validation-contract";
export const dynamic = "force-dynamic";
const projectPattern = /^[0-9a-f-]{36}$/i;
const idPattern = /^[A-Z]{2,5}-\d{3,}$/;
// Validation plans: POST generate (model call), POST <id>/approve, GET <id>.
async function proxy(request: Request, context: { params: Promise<{ segments: string[] }> }) {
    const { segments } = await context.params;
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number, uncertain = false) => Response.json({ message, uncertain }, { status, headers });
    const params = new URL(request.url).searchParams;
    let projectId = params.get("project_id") ?? "";
    let setId = "";
    const generate = request.method === "POST" && segments.length === 1 && segments[0] === "generate";
    const approve = request.method === "POST" && segments.length === 2 && idPattern.test(segments[0]) && segments[1] === "approve";
    const read = request.method === "GET" && segments.length === 1 && idPattern.test(segments[0]);
    if (!generate && !approve && !read)
        return fail("Unsupported validation action.", 400);
    if (request.method === "POST") {
        try {
            const input = await request.json();
            projectId = input.project_id;
            setId = input.requirements_set_id ?? "";
        }
        catch {
            return fail("Invalid request body.", 400);
        }
    }
    if (typeof projectId !== "string" || !projectPattern.test(projectId) || (generate && !/^RSET-\d+$/.test(setId)))
        return fail("A valid project and requirements set are required.", 422);
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Validation service is not configured.", 503);
    const url = `${base.replace(/\/$/, "")}/projects/${projectId}/validation-plans${generate ? "" : `/${segments.join("/")}`}`;
    try {
        const response = await fetch(url, { method: request.method, headers: { "Content-Type": "application/json" }, body: generate ? JSON.stringify({ requirements_set_id: setId }) : approve ? "{}" : undefined, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(generate ? 300000 : 15000) });
        if (!response.ok) {
            const detail = await response.json().then((b: { detail?: unknown; message?: unknown }) => typeof b?.detail === "string" ? b.detail : typeof b?.message === "string" ? b.message : "", () => "");
            return fail(detail.slice(0, 300) || "The validation plan request failed.", response.status >= 500 ? 502 : response.status, generate && response.status >= 500);
        }
        return Response.json(parseValidationPlan(await response.json()), { headers });
    }
    catch {
        return fail(generate ? "Generation could not be confirmed. Check before generating again." : "Could not reach the validation service.", 502, generate);
    }
}
export { proxy as GET, proxy as POST };
