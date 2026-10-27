import { parseArchitecture } from "@/lib/api/architecture-contract";
export const dynamic = "force-dynamic";
async function proxy(request: Request, context: {
    params: Promise<{
        segments: string[];
    }>;
}) {
    const { segments } = await context.params;
    const path = segments.join("/");
    const read = request.method === "GET" && /^ARCH-\d+$/.test(path);
    const generate = request.method === "POST" && path === "generate";
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number, uncertain = false) => Response.json({ message, uncertain }, { status, headers });
    if (!read && !generate)
        return fail("Unsupported architecture action.", 400);
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Architecture service is not configured. Contact the workspace operator.", 503);
    let body;
    if (generate) {
        try {
            const input = await request.json();
            if (typeof input.project_id !== "string" || !/^[0-9a-f-]{36}$/i.test(input.project_id) || typeof input.requirements_set_id !== "string" || !/^RSET-\d+$/.test(input.requirements_set_id))
                return fail("Enter a locked requirements set ID such as RSET-001.", 422);
            if (input.context !== undefined && (typeof input.context !== "string" || input.context.length > 20000))
                return fail("Design context must be at most 20,000 characters.", 422);
            body = { project_id: input.project_id, requirements_set_id: input.requirements_set_id, context: input.context ?? "" };
        }
        catch {
            return fail("Invalid request body.", 400);
        }
    }
    let sent = false;
    try {
        const url = new URL(base.replace(/\/$/, "") + "/architecture/" + path);
        if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
            return fail("Architecture service URL is invalid.", 503);
        sent = true;
        const response = await fetch(url, { method: request.method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined, cache: "no-store", redirect: "error", signal: AbortSignal.timeout(generate ? 180000 : 8000) });
        if (!response.ok) {
            const messages: Record<number, string> = { 404: "This architecture was not found for the project. Confirm its ID or contact the backend owner.", 409: "The architecture status changed. Reload the saved document.", 422: "Architecture generation was rejected. The requirements set must exist and be locked.", 503: "The model runtime or architecture service is unavailable. Contact the workspace operator." };
            return fail(messages[response.status] ?? "Architecture service failed. Reload saved records before retrying generation.", response.status >= 500 ? 502 : response.status, generate && response.status >= 500);
        }
        return Response.json(parseArchitecture(await response.json()), { headers });
    }
    catch {
        return fail(read ? "Could not load the architecture. Try again." : "Generation could not be confirmed. Open the saved architecture before generating again.", 502, generate && sent);
    }
}
export { proxy as GET, proxy as POST };
