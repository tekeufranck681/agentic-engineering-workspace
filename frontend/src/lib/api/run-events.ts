// One persisted run event as streamed by GET /runs/{id}/events/stream.
// `type` is the backend event name (e.g. "evaluation.completed"); the backend
// is authoritative, so unknown types are kept and rendered generically.
export type RunEvent = {
    sequence: number;
    type: string;
    payload: Record<string, unknown>;
};
export type AcVerdict = {
    acceptance_criterion_id: string;
    verdict: "PASS" | "FAIL" | "UNVERIFIED";
    reason: string;
    evidence_ids: string[];
};
export function parseEvent(sequence: string | number, type: string, data: string): RunEvent | null {
    const seq = typeof sequence === "number" ? sequence : Number.parseInt(sequence, 10);
    if (!Number.isInteger(seq) || seq < 1 || !/^[a-z_]+(\.[a-z_]+)*$/.test(type))
        return null;
    try {
        const payload = JSON.parse(data);
        return { sequence: seq, type, payload: payload && typeof payload === "object" && !Array.isArray(payload) ? payload : {} };
    }
    catch {
        return null;
    }
}
export function verdictsOf(event: RunEvent): AcVerdict[] {
    const raw = event.payload.verdicts;
    if (!Array.isArray(raw))
        return [];
    return raw.flatMap(v => {
        if (!v || typeof v !== "object")
            return [];
        const r = v as Record<string, unknown>;
        const verdict = r.verdict === "PASS" || r.verdict === "FAIL" || r.verdict === "UNVERIFIED" ? r.verdict : null;
        if (typeof r.acceptance_criterion_id !== "string" || !verdict)
            return [];
        return [{ acceptance_criterion_id: r.acceptance_criterion_id, verdict, reason: typeof r.reason === "string" ? r.reason : "", evidence_ids: Array.isArray(r.evidence_ids) ? r.evidence_ids.filter((e): e is string => typeof e === "string") : [] }];
    });
}
// Merge is idempotent and ordered: replays after a reconnect never duplicate.
export function mergeEvents(current: RunEvent[], incoming: RunEvent[]): RunEvent[] {
    const bySeq = new Map(current.map(e => [e.sequence, e]));
    for (const e of incoming)
        if (!bySeq.has(e.sequence))
            bySeq.set(e.sequence, e);
    return [...bySeq.values()].sort((a, b) => a.sequence - b.sequence);
}
