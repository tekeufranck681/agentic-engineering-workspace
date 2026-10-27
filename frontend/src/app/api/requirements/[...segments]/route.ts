import { parseCriteria, parseRequirements } from "@/lib/api/requirements-contract";
export const dynamic = "force-dynamic";
async function proxy(request: Request, context: {
    params: Promise<{
        segments: string[];
    }>;
}) {
    const { segments } = await context.params;
    const path = segments.join("/");
    if (/^set\/RSET-\d+\/acceptance-criteria$/.test(path))
        return criteria(request, path);
    const read = request.method === "GET" && /^set\/RSET-\d+$/.test(path);
    const analyze = request.method === "POST" && path === "analyze";
    const transition = request.method === "POST" && /^set\/RSET-\d+\/(approve|lock)$/.test(path);
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number, uncertain = false) => Response.json({ message, uncertain }, { status, headers });
    if (!read && !analyze && !transition)
        return fail("Unsupported requirements action.", 400);
    const projectId = new URL(request.url).searchParams.get("project_id") ?? "";
    if (read && !/^[0-9a-f-]{36}$/i.test(projectId))
        return fail("A valid project is required to open a requirements set.", 422);
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Requirements service is not configured. Contact the workspace operator.", 503);
    let body;
    if (!read) {
        try {
            const input = await request.json();
            if (analyze) {
                if (typeof input.project_id !== "string" || !/^[0-9a-f-]{36}$/i.test(input.project_id) || typeof input.brief !== "string" || !input.brief.trim() || input.brief.length > 20000)
                    return fail("Enter a project brief of 1–20,000 characters.", 422);
                body = { project_id: input.project_id, brief: input.brief };
            }
            else {
                const key = path.endsWith("approve") ? "approved_by" : "locked_by";
                if (typeof input[key] !== "string" || !input[key].trim() || input[key].length > 200)
                    return fail("Enter a reviewer name of 1–200 characters.", 422);
                if (typeof input.project_id !== "string" || !/^[0-9a-f-]{36}$/i.test(input.project_id))
                    return fail("A valid project is required.", 422);
                body = { [key]: input[key].trim(), project_id: input.project_id };
            }
        }
        catch {
            return fail("Invalid request body.", 400);
        }
    }
    let sent = false;
    try {
        const url = new URL(base.replace(/\/$/, "") + "/requirements/" + path);
        if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
            return fail("Requirements service URL is invalid.", 503);
        if (read)
            url.searchParams.set("project_id", projectId);
        sent = true;
        const response = await fetch(url, { method: request.method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(analyze ? 120000 : 8000) });
        if (!response.ok) {
            const messages: Record<number, string> = { 404: "This requirements set was not found for the project. Confirm its ID or contact the backend owner.", 409: "The requirements status changed or this transition is not allowed. Reload the saved set.", 422: "The requirements request was rejected. Check your brief and reviewer details.", 503: "The model runtime or requirements service is unavailable. Contact the workspace operator." };
            return fail(messages[response.status] ?? "Requirements service failed. Reload saved records before retrying a write.", response.status >= 500 ? 502 : response.status, !read && response.status >= 500);
        }
        return Response.json(parseRequirements(await response.json()), { headers });
    }
    catch {
        return fail(read ? "Could not load requirements. Try again." : "The operation could not be confirmed. Open the saved set before submitting again.", 502, !read && sent);
    }
}
export { proxy as GET, proxy as POST };

// Acceptance criteria for a set: GET lists them, POST generates them (one
// model call per requirement, so it gets a long timeout).
async function criteria(request: Request, path: string) {
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number, uncertain = false) => Response.json({ message, uncertain }, { status, headers });
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Requirements service is not configured. Contact the workspace operator.", 503);
    const generate = request.method === "POST";
    let projectId = new URL(request.url).searchParams.get("project_id") ?? "";
    if (generate) {
        try {
            projectId = (await request.json()).project_id;
        }
        catch {
            return fail("Invalid request body.", 400);
        }
    }
    if (typeof projectId !== "string" || !/^[0-9a-f-]{36}$/i.test(projectId))
        return fail("A valid project is required.", 422);
    const url = new URL(base.replace(/\/$/, "") + "/requirements/" + path);
    if (!generate)
        url.searchParams.set("project_id", projectId);
    try {
        const response = await fetch(url, { method: request.method, headers: { "Content-Type": "application/json" }, body: generate ? JSON.stringify({ project_id: projectId }) : undefined, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(generate ? 300000 : 8000) });
        if (!response.ok) {
            const detail = await response.json().then((b: { detail?: unknown }) => (typeof b?.detail === "string" ? b.detail.slice(0, 300) : ""), () => "");
            return fail(detail || (response.status === 503 ? "The model runtime is unavailable." : "Acceptance criteria could not be loaded."), response.status >= 500 ? 502 : response.status, generate && response.status >= 500);
        }
        return Response.json({ acceptance_criteria: parseCriteria(await response.json()) }, { headers });
    }
    catch {
        return fail(generate ? "Generation could not be confirmed. Reload the criteria before generating again." : "Could not load acceptance criteria.", 502, generate);
    }
}
