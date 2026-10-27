"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, CircleDashed, FileCode2, GitPullRequest, LoaderCircle, RefreshCw, Stethoscope, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/status-badge";
import { useRunsStore, runKey, type Connection } from "@/stores/runsStore";
import { verdictsOf, type RunEvent } from "@/lib/api/runs-contract";
import styles from "./runs.module.css";
type Tone = "neutral" | "pass" | "fail" | "warn" | "live";
type Described = {
    phase: string;
    title: string;
    detail?: string;
    tone: Tone;
};
const str = (v: unknown) => (typeof v === "string" ? v : "");
const list = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : []);
// Turns a persisted backend event into one readable line. Unknown event types
// are still shown with their raw name; nothing here invents progress.
export function describe(event: RunEvent): Described {
    const p = event.payload;
    switch (event.type) {
        case "run.loaded": return { phase: "Setup", title: `Loaded ${str(p.task_id) || "task"} with ${list(p.ac_ids).length} acceptance criteria`, detail: p.readiness ? `Readiness: ${str(p.readiness)}` : undefined, tone: "neutral" };
        case "run.status": return { phase: "Status", title: `Run is ${str(p.status)}`, detail: str(p.error) || undefined, tone: p.status === "failed" ? "fail" : "neutral" };
        case "run.blocked": return { phase: "Setup", title: "Run blocked before any change", detail: str(p.reasons), tone: "fail" };
        case "context.built": return { phase: "Context", title: "Context assembled", detail: [p.chars ? `${p.chars} characters` : "", p.degraded ? "degraded: some sources were unavailable" : ""].filter(Boolean).join(" · ") || undefined, tone: p.degraded ? "warn" : "neutral" };
        case "implementation.applied": return { phase: "Implementation", title: `Changed ${list(p.written).length} file${list(p.written).length === 1 ? "" : "s"}`, detail: list(p.rejected).length ? `${list(p.rejected).length} edit(s) rejected outside the task scope` : str(p.summary) || undefined, tone: "neutral" };
        case "implementation.failed": return { phase: "Implementation", title: `Attempt ${p.attempt ?? "?"} produced no usable change`, detail: str(p.error), tone: "fail" };
        case "evaluation.completed": {
            const failing = verdictsOf(event).filter(v => v.verdict !== "PASS");
            return p.passed === true
                ? { phase: "Evaluation", title: "Independent evaluation passed", detail: `${verdictsOf(event).length} acceptance criteria verified`, tone: "pass" }
                : { phase: "Evaluation", title: `Evaluation failed on ${failing.map(v => v.acceptance_criterion_id).join(", ") || "acceptance criteria"}`, detail: failing[0]?.reason, tone: "fail" };
        }
        case "diagnosis.completed": return { phase: "Diagnosis", title: `Diagnosed: ${str(p.cause) || "cause recorded"}`, detail: str(p.required_change) ? `Correction: ${str(p.required_change)}` : undefined, tone: "warn" };
        case "delivery.started": return { phase: "Delivery", title: "Delivery gates started", tone: "neutral" };
        case "delivery.gates_passed": return { phase: "Delivery", title: `Gates passed with ${p.tests_passed ?? 0} passing tests`, tone: "pass" };
        case "delivery.refused": return { phase: "Delivery", title: "Delivery refused", detail: str(p.reason), tone: "fail" };
        case "delivery.pr_opened": return { phase: "Delivery", title: `Pull request #${p.pr_number} opened`, detail: str(p.branch), tone: "pass" };
        case "run.finished": return { phase: "Result", title: p.status === "succeeded" ? `Run succeeded after ${p.attempts ?? "?"} attempt(s)` : `Run failed${p.error ? `: ${str(p.error)}` : ""}`, tone: p.status === "succeeded" ? "pass" : "fail" };
        default: return { phase: event.type.split(".")[0], title: event.type, tone: "neutral" };
    }
}
// Groups the ordered event list into setup, numbered attempts and delivery.
function groupByAttempt(events: RunEvent[]) {
    const groups: { label: string; events: RunEvent[] }[] = [];
    let current = "Setup";
    for (const e of events) {
        const attempt = typeof e.payload.attempt === "number" ? e.payload.attempt : null;
        let label = current;
        if (e.type.startsWith("delivery."))
            label = "Delivery";
        else if (e.type === "run.finished")
            label = "Result";
        else if (attempt !== null)
            label = `Attempt ${attempt}`;
        else if (e.type === "implementation.applied")
            label = current.startsWith("Attempt") ? current : "Attempt 1";
        current = label;
        const last = groups.at(-1);
        if (last && last.label === label)
            last.events.push(e);
        else
            groups.push({ label, events: [e] });
    }
    return groups;
}
const connectionCopy: Record<Connection, string> = { idle: "Not connected", connecting: "Connecting to event stream", live: "Live", reconnecting: "Connection lost. Reconnecting", finished: "Run finished. Stream closed", error: "Stream unavailable" };
const ToneIcon = ({ tone }: { tone: Tone }) => tone === "pass" ? <CheckCircle2 size={14} aria-hidden="true"/> : tone === "fail" ? <XCircle size={14} aria-hidden="true"/> : tone === "warn" ? <Stethoscope size={14} aria-hidden="true"/> : <CircleDashed size={14} aria-hidden="true"/>;
function Inspector({ event }: { event: RunEvent }) {
    const d = describe(event);
    const p = event.payload;
    const verdicts = verdictsOf(event);
    return <div className={styles.inspectorBody}>
  <div className={styles.inspectorMeta}><code>#{event.sequence}</code><span>{event.type}</span></div>
  <h3>{d.title}</h3>
  {d.detail && <p className={styles.inspectorDetail}>{d.detail}</p>}
  {verdicts.length > 0 && <><h4>Acceptance criteria</h4><table className={styles.verdicts}><thead><tr><th>Criterion</th><th>Verdict</th><th>Reason</th></tr></thead><tbody>{verdicts.map(v => <tr key={v.acceptance_criterion_id} data-verdict={v.verdict}><td><code>{v.acceptance_criterion_id}</code></td><td><span className={styles.verdict}>{v.verdict === "PASS" ? <CheckCircle2 size={12} aria-hidden="true"/> : <XCircle size={12} aria-hidden="true"/>}{v.verdict.toLowerCase()}</span></td><td>{v.reason || "No reason recorded"}{v.evidence_ids.length > 0 && <span className={styles.evidence}>{v.evidence_ids.join(", ")}</span>}</td></tr>)}</tbody></table></>}
  {list(p.written).length > 0 && <><h4>Files changed</h4><ul className={styles.files}>{list(p.written).map(f => <li key={f}><FileCode2 size={12} aria-hidden="true"/><code>{f}</code></li>)}</ul></>}
  {list(p.rejected).length > 0 && <><h4>Rejected edits</h4><ul className={styles.files}>{list(p.rejected).map(f => <li key={f} data-rejected><XCircle size={12} aria-hidden="true"/><code>{f}</code></li>)}</ul></>}
  {event.type === "diagnosis.completed" && <><h4>Failing criteria</h4><p>{list(p.failing_ac_ids).join(", ") || "None recorded"}</p>{list(p.narrowed_paths).length > 0 && <><h4>Correction scope</h4><ul className={styles.files}>{list(p.narrowed_paths).map(f => <li key={f}><code>{f}</code></li>)}</ul></>}</>}
  {event.type === "delivery.pr_opened" && typeof p.pr_url === "string" && /^https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+$/.test(p.pr_url) && <a className={styles.prLink} href={p.pr_url} target="_blank" rel="noopener noreferrer"><GitPullRequest size={14} aria-hidden="true"/>Open pull request #{String(p.pr_number)}</a>}
  <details className={styles.raw}><summary>Recorded payload</summary><pre>{JSON.stringify(p, null, 2)}</pre></details>
 </div>;
}
export function RunsWorkspace({ projectId }: { projectId: string }) {
    const listEntry = useRunsStore(s => s.lists[projectId]);
    const loadList = useRunsStore(s => s.loadList);
    const loadDetail = useRunsStore(s => s.loadDetail);
    const follow = useRunsStore(s => s.follow);
    const [selectedRun, setSelectedRun] = useState<string>();
    const [selectedSeq, setSelectedSeq] = useState<number>();
    const preview = projectId === "preview";
    const runs = useMemo(() => [...(listEntry?.data ?? [])].sort((a, b) => b.id.localeCompare(a.id, undefined, { numeric: true })), [listEntry?.data]);
    const runId = selectedRun ?? runs[0]?.id;
    const state = useRunsStore(s => (runId ? s.runs[runKey(projectId, runId)] : undefined));
    useEffect(() => { if (!preview)
        void loadList(projectId); }, [loadList, preview, projectId]);
    useEffect(() => {
        if (preview || !runId)
            return;
        void loadDetail(projectId, runId);
        return follow(projectId, runId);
    }, [follow, loadDetail, preview, projectId, runId]);
    const events = state?.events ?? [];
    const groups = groupByAttempt(events);
    const selected = events.find(e => e.sequence === selectedSeq) ?? [...events].reverse().find(e => describe(e).tone === "fail") ?? events.at(-1);
    const run = state?.detail?.run ?? runs.find(r => r.id === runId);
    const task = state?.detail?.task;
    const attempts = new Set(events.map(e => e.payload.attempt).filter(a => typeof a === "number")).size;
    const connection = state?.connection ?? "idle";
    return <div className={`workspace-page ${styles.page}`}>
  <header className={styles.header}>
   <div className={styles.titleBlock}>
    <h1>Agent Runs</h1>
    <p>What ran, what failed, why, and what fixed it. Every line below is a persisted event.</p>
   </div>
   {!preview && <Button variant="outline" size="sm" disabled={listEntry?.pending} onClick={() => void loadList(projectId)}>{listEntry?.pending ? <LoaderCircle size={14} className="animate-spin" aria-hidden="true"/> : <RefreshCw size={14} aria-hidden="true"/>}Refresh runs</Button>}
  </header>
  {preview && <p className="workspace-notice">Preview mode. Open a saved project to follow its real runs.</p>}
  {listEntry?.error && <div className="requirements-error" role="alert"><AlertCircle size={16} aria-hidden="true"/><div><strong>Runs could not be loaded</strong><p>{listEntry.error}</p></div></div>}
  <div className={styles.layout}>
   <nav className={styles.runList} aria-label="Runs">
    <h2>Runs <span>{listEntry?.data ? runs.length : "—"}</span></h2>
    {runs.length ? <ul>{runs.map(r => <li key={r.id}><button type="button" aria-current={r.id === runId ? "true" : undefined} onClick={() => { setSelectedRun(r.id); setSelectedSeq(undefined); }}><code className={styles.runId}>{r.id}</code><span className={styles.runMeta}>{r.task_id} · attempt {r.attempt}</span><span className={styles.runBadge}><StatusBadge>{r.status}</StatusBadge></span></button></li>)}</ul>
            : <p className={styles.muted}>{listEntry?.data ? "No runs yet. A run starts from a ready task in Planning." : "Runs appear here once loaded."}</p>}
    <Link href={`/projects/${projectId}/planning`} className={styles.sideLink}>Go to Planning</Link>
   </nav>
   <section className={styles.trace} aria-labelledby="run-trace-title">
    <div className={styles.runHeader}>
     <div>
      <h2 id="run-trace-title">{run ? <><code>{run.id}</code>{task ? task.title : run.task_id}</> : "No run selected"}</h2>
      {run && <p>{task ? <><code>{task.id}</code> · {task.ac_ids.length} acceptance criteria · </> : null}{attempts || run.attempt} attempt{(attempts || run.attempt) === 1 ? "" : "s"}{run.error ? ` · ${run.error}` : ""}</p>}
     </div>
     {run && <div className={styles.runStatus}><StatusBadge>{run.status}</StatusBadge><span className={styles.connection} data-state={connection} role="status">{(connection === "connecting" || connection === "reconnecting") && <LoaderCircle size={12} className="animate-spin" aria-hidden="true"/>}{connectionCopy[connection]}</span></div>}
    </div>
    {state?.streamError && <p className={styles.streamError} role="alert">{state.streamError}</p>}
    {!events.length ? <div className={styles.empty}><h3>{run ? (connection === "connecting" ? "Opening the event stream" : "No events recorded yet") : "Nothing to trace yet"}</h3><p>{run ? "Events appear in order as the orchestrator records them. Nothing is shown until it is persisted." : "Select a run, or start one from a ready task."}</p></div>
            : <ol className={styles.groups}>{groups.map((g, gi) => <li key={`${g.label}-${gi}`} className={styles.group} data-kind={g.label.startsWith("Attempt") ? "attempt" : g.label.toLowerCase()}>
       <h3>{g.label}</h3>
       <ol className={styles.events}>{g.events.map(e => { const d = describe(e); return <li key={e.sequence}><button type="button" className={styles.event} data-tone={d.tone} aria-pressed={selected?.sequence === e.sequence} onClick={() => setSelectedSeq(e.sequence)}>
         <span className={styles.seq}>{e.sequence}</span><span className={styles.node}><ToneIcon tone={d.tone}/></span>
         <span className={styles.eventText}><span className={styles.phase}>{d.phase}</span><strong>{d.title}</strong>{d.detail && <span className={styles.detail}>{d.detail}</span>}</span>
        </button></li>; })}</ol>
      </li>)}</ol>}
   </section>
   <aside className={styles.inspector} aria-label="Event inspector">
    <h2>Event</h2>
    {selected ? <Inspector event={selected}/> : <p className={styles.muted}>Select an event to inspect its recorded verdicts, files and payload.</p>}
   </aside>
  </div>
 </div>;
}
