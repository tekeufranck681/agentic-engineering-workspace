import { apiRequest } from "@/lib/api/client";
import { parseEvent, parseRunDetail, parseRuns, type RunEvent } from "@/lib/api/runs-contract";
const query = (projectId: string) => `?project_id=${encodeURIComponent(projectId)}`;
export const runsService = {
    list: (projectId: string) => apiRequest(`/runs/list${query(projectId)}`, parseRuns),
    detail: (projectId: string, runId: string) => apiRequest(`/runs/${encodeURIComponent(runId)}${query(projectId)}`, parseRunDetail),
    // Reads the SSE stream frame by frame. Resolves "finished" when the server
    // reports a terminal run, "ended" if the connection closes without one.
    stream: async (projectId: string, runId: string, after: number, onEvent: (event: RunEvent) => void, signal: AbortSignal): Promise<"finished" | "ended"> => {
        const response = await fetch(`/api/runs/${encodeURIComponent(runId)}/events${query(projectId)}&after=${after}`, { headers: { Accept: "text/event-stream" }, cache: "no-store", signal });
        if (!response.ok || !response.body)
            throw new Error(response.status === 404 ? "This run has no event stream." : "Could not open the run event stream.");
        const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
        let buffer = "";
        for (;;) {
            const { value, done } = await reader.read();
            if (done)
                return "ended";
            buffer += value;
            let split: number;
            while ((split = buffer.indexOf("\n\n")) >= 0) {
                const frame = buffer.slice(0, split);
                buffer = buffer.slice(split + 2);
                let id = "", type = "", data = "";
                for (const line of frame.split("\n")) {
                    if (line.startsWith("id: "))
                        id = line.slice(4);
                    else if (line.startsWith("event: "))
                        type = line.slice(7);
                    else if (line.startsWith("data: "))
                        data += line.slice(6);
                }
                if (type === "run_finished")
                    return "finished";
                const event = id && type ? parseEvent(id, type, data) : null;
                if (event)
                    onEvent(event);
            }
        }
    },
};
