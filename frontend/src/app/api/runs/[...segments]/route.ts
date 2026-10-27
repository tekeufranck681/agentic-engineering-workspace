import { parseRunDetail, parseRuns } from "@/lib/api/runs-contract";
export const dynamic = "force-dynamic";
const projectPattern = /^[0-9a-f-]{36}$/i;
export async function GET(request: Request, context: {
    params: Promise<{
        segments: string[];
    }>;
}) {
    const { segments } = await context.params;
    const path = segments.join("/");
    const params = new URL(request.url).searchParams;
    const projectId = params.get("project_id") ?? "";
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number) => Response.json({ message, uncertain: false }, { status, headers });
    const list = path === "list";
    const detail = /^RUN-\d+$/.test(path);
    const stream = /^RUN-\d+\/events$/.test(path);
    if (!list && !detail && !stream)
        return fail("Unsupported runs action.", 400);
    if (!projectPattern.test(projectId))
        return fail("A valid project is required.", 422);
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Run service is not configured. Contact the workspace operator.", 503);
    const root = base.replace(/\/$/, "");
    let url: URL;
    try {
        url = new URL(list ? `${root}/runs` : stream ? `${root}/runs/${segments[0]}/events/stream` : `${root}/runs/${path}`);
    }
    catch {
        return fail("Run service URL is invalid.", 503);
    }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
        return fail("Run service URL is invalid.", 503);
    if (stream) {
        // Resume from the browser's Last-Event-ID (or ?after=) so a reconnect
        // replays only events the client has not seen.
        const after = request.headers.get("last-event-id") ?? params.get("after");
        if (after && /^\d+$/.test(after))
            url.searchParams.set("after", after);
        try {
            const upstream = await fetch(url, { headers: { Accept: "text/event-stream" }, cache: "no-store", redirect: "error", signal: request.signal });
            if (!upstream.ok || !upstream.body)
                return fail(upstream.status === 404 ? "This run has no event stream." : "Could not open the run event stream.", upstream.status === 404 ? 404 : 502);
            return new Response(upstream.body, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-store, no-transform", Connection: "keep-alive" } });
        }
        catch {
            return fail("Could not reach the run event stream.", 502);
        }
    }
    url.searchParams.set("project_id", projectId);
    try {
        const response = await fetch(url, { cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8000) });
        if (!response.ok)
            return fail(response.status === 404 ? "This run was not found for the project." : "Could not load runs. Try again.", response.status === 404 ? 404 : 502);
        const body = await response.json();
        return Response.json(list ? parseRuns(body) : parseRunDetail(body), { headers });
    }
    catch {
        return fail("Could not reach the run service. Try again.", 502);
    }
}
