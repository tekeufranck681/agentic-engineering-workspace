import { parseDeliveries, parseRuns } from "@/lib/api/delivery-contract";
export const dynamic = "force-dynamic";
export async function GET(request: Request, context: {
    params: Promise<{
        segments: string[];
    }>;
}) {
    const { segments } = await context.params;
    const path = segments.join("/");
    const projectId = new URL(request.url).searchParams.get("project_id") ?? "";
    const headers = { "Cache-Control": "no-store" };
    const fail = (message: string, status: number) => Response.json({ message, uncertain: false }, { status, headers });
    if (path !== "traceability" && path !== "runs")
        return fail("Unsupported delivery action.", 400);
    if (!/^[0-9a-f-]{36}$/i.test(projectId))
        return fail("A valid project is required.", 422);
    const base = process.env.BACKEND_API_URL;
    if (!base)
        return fail("Delivery service is not configured. Contact the workspace operator.", 503);
    try {
        const root = base.replace(/\/$/, "");
        const url = new URL(path === "runs" ? `${root}/runs` : `${root}/projects/${projectId}/traceability`);
        if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
            return fail("Delivery service URL is invalid.", 503);
        if (path === "runs")
            url.searchParams.set("project_id", projectId);
        const response = await fetch(url, { cache: "no-store", redirect: "error", signal: AbortSignal.timeout(8000) });
        if (response.status === 404 || response.status === 405)
            return fail(path === "runs" ? "Runs are not available for this project." : "The delivery traceability API is not available yet. No pull request can be shown.", 404);
        if (!response.ok)
            return fail(path === "runs" ? "Could not load runs. Try again." : "Could not load delivery evidence. Try again.", 502);
        const body = await response.json();
        return Response.json(path === "runs" ? parseRuns(body) : parseDeliveries(body), { headers });
    }
    catch {
        return fail("Could not reach the delivery service. Try again.", 502);
    }
}
