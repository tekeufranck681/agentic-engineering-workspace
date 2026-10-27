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
// Starting work is two server-confirmed steps: create a queued run for a
// ready task, then ask the orchestrator to execute it.
export async function POST(request: Request, context: {
    params: Promise<{
        segments: string[];
    }>;
}) {
    const { segments } = await context.params;
    const path = segments.join("/");
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number, uncertain = false) => Response.json({ message, uncertain }, { status, headers });
    const start = path === "start";
    const execute = /^RUN-\d+\/execute$/.test(path);
    if (!start && !execute)
        return fail("Unsupported runs action.", 400);
    let input: { project_id?: unknown; task_id?: unknown };
    try {
        input = await request.json();
    }
    catch {
        return fail("Invalid request body.", 400);
    }
    if (typeof input.project_id !== "string" || !projectPattern.test(input.project_id) || (start && (typeof input.task_id !== "string" || !/^TASK-\d+$/.test(input.task_id))))
        return fail("A valid project and task are required.", 422);
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Run service is not configured. Contact the workspace operator.", 503);
    try {
        const response = await fetch(`${base.replace(/\/$/, "")}/runs/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(start ? { project_id: input.project_id, task_id: input.task_id } : { project_id: input.project_id }), cache: "no-store", redirect: "error", signal: AbortSignal.timeout(15000) });
        const body = await response.json().catch(() => ({}));
        if (!response.ok)
            return fail(typeof body?.detail === "string" ? body.detail.slice(0, 300) : "The run could not be started.", response.status >= 500 ? 502 : response.status, response.status >= 500);
        if (start) {
            const run = body?.run;
            if (!run || typeof run.id !== "string")
                return fail("The run could not be confirmed. Check Agent Runs before starting again.", 502, true);
            return Response.json({ run_id: run.id }, { headers });
        }
        return Response.json({ run_id: segments[0], accepted: body?.accepted === true }, { headers });
    }
    catch {
        return fail("The run could not be confirmed. Check Agent Runs before starting again.", 502, true);
    }
}
