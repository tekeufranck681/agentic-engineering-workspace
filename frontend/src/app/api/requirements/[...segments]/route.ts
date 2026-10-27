import { parseRequirements } from "@/lib/api/requirements-contract";
export const dynamic = "force-dynamic";
async function proxy(request: Request, context: {
    params: Promise<{
        segments: string[];
    }>;
}) {
    const { segments } = await context.params;
    const path = segments.join("/");
    const read = request.method === "GET" && /^set\/RSET-\d+$/.test(path);
    const analyze = request.method === "POST" && path === "analyze";
    const transition = request.method === "POST" && /^set\/RSET-\d+\/(approve|lock)$/.test(path);
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number, uncertain = false) => Response.json({ message, uncertain }, { status, headers });
    if (!read && !analyze && !transition)
        return fail("Unsupported requirements action.", 400);
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
                body = { [key]: input[key].trim() };
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
