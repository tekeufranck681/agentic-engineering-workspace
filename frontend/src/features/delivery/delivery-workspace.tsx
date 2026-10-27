"use client";
import { useEffect } from "react";
import Link from "next/link";
import { AlertCircle, ExternalLink, FileDiff, GitBranch, GitPullRequest, LoaderCircle, RefreshCw, ShieldCheck, Waypoints } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/status-badge";
import { useDeliveryStore } from "@/stores/deliveryStore";
import { usePlanningStore } from "@/stores/planningStore";
import { useRequirementsStore } from "@/stores/requirementsStore";
import type { Delivery, RunSummary } from "@/lib/api/delivery-contract";
const short = (sha: string) => sha.slice(0, 7);
// A run's PR state is derived only from persisted records: a Delivery record
// confirms the PR; a failed run is an error; anything else is still pending.
function prState(run: RunSummary | undefined, delivery: Delivery | undefined) {
    if (delivery)
        return "confirmed";
    if (!run)
        return "not started";
    if (run.status === "failed" || run.status === "cancelled")
        return "error";
    return "pending";
}
function EvidenceViewer({ delivery }: {
    delivery: Delivery;
}) {
    return <article className="delivery-card">
  <header><GitPullRequest size={16} aria-hidden="true"/><a href={delivery.pr_url} target="_blank" rel="noopener noreferrer" className="delivery-pr-link">Pull request #{delivery.pr_number}<ExternalLink size={13} aria-hidden="true"/></a><StatusBadge>{delivery.tests_passed > 0 ? `${delivery.tests_passed} tests passed` : "No passing tests recorded"}</StatusBadge></header>
  <dl className="delivery-meta">
   <div><dt>Task</dt><dd><code>{delivery.task_id}</code></dd></div>
   <div><dt>Run</dt><dd><code>{delivery.run_id}</code></dd></div>
   <div><dt>Branch</dt><dd><code><GitBranch size={12} aria-hidden="true"/> {delivery.branch}</code></dd></div>
   <div><dt>Commit</dt><dd><code title={delivery.commit_sha}>{short(delivery.commit_sha)}</code> on <code title={delivery.base_sha}>{short(delivery.base_sha)}</code></dd></div>
  </dl>
  <h4><FileDiff size={13} aria-hidden="true"/>Changed files <span className="field-hint">{delivery.changed_paths.length}</span></h4>
  {delivery.changed_paths.length ? <ul className="task-paths">{delivery.changed_paths.map(p => <li key={p}><a href={`${delivery.pr_url.replace(/\/$/, "")}/files`} target="_blank" rel="noopener noreferrer"><code>{p}</code></a></li>)}</ul> : <p className="field-hint">No changed files recorded.</p>}
  <h4><ShieldCheck size={13} aria-hidden="true"/>Evidence</h4>
  {delivery.evidence.length ? <ul className="arch-chip-list">{delivery.evidence.map(e => <li key={`${e.kind}:${e.id}`}><span className="arch-chip" title={e.kind}>{e.kind}: {e.id}</span></li>)}</ul> : <p className="field-hint">No evidence references recorded.</p>}
 </article>;
}
export function DeliveryWorkspace({ projectId }: {
    projectId: string;
}) {
    const entry = useDeliveryStore(s => s.entries[projectId]);
    const load = useDeliveryStore(s => s.load);
    const tasks = usePlanningStore(s => s.entries[projectId]?.data?.tasks);
    const requirements = useRequirementsStore(s => s.entries[projectId]?.data?.requirements);
    const preview = projectId === "preview";
    useEffect(() => { if (!preview)
        void load(projectId); }, [load, preview, projectId]);
    const deliveries = entry?.deliveries.data ?? [];
    const runs = entry?.runs.data ?? [];
    const latestRun = (taskId: string) => runs.filter(r => r.task_id === taskId).sort((a, b) => b.attempt - a.attempt)[0];
    const deliveryFor = (taskId: string) => deliveries.find(d => d.task_id === taskId);
    // Delivered only when every PR has passing tests and, if a plan is loaded,
    // every planned task has a PR. Anything less is reported as partial.
    const verified = deliveries.length > 0 && deliveries.every(d => d.tests_passed > 0);
    const complete = verified && (tasks ?? []).every(t => deliveries.some(d => d.task_id === t.id));
    const summary = preview ? "Preview" : entry?.pending && !entry.deliveries.data ? "Loading" : entry?.deliveries.error ? "Blocked" : complete ? "Delivered" : deliveries.length ? "Partially delivered" : "Not delivered";
    const requirementsHref = `/projects/${projectId}/requirements`;
    const planningHref = `/projects/${projectId}/planning`;
    const acRows = (requirements ?? []).flatMap(r => (r.trace.ac_ids.length ? r.trace.ac_ids : [null]).map(ac => ({ requirement: r.id, ac, tasks: (tasks ?? []).filter(t => ac ? t.ac_ids.includes(ac) : t.requirement_ids.includes(r.id)) })));
    return <div className="workspace-page delivery-page">
  <div className="page-heading"><div><h1>Delivery</h1><p className="page-description">Verify what changed, why it passed, and the resulting GitHub pull request.</p></div><StatusBadge>{summary}</StatusBadge></div>
  {preview && <p className="workspace-notice">Preview mode. Open a saved project to inspect real delivery evidence.</p>}
  {!preview && <div className="open-set-bar"><Waypoints size={16} aria-hidden="true"/><span>Delivery records are created after an evaluation passes. Nothing is shown as delivered without a confirmed pull request.</span><Button variant="outline" disabled={entry?.pending} onClick={() => void load(projectId)}>{entry?.pending ? <LoaderCircle size={14} className="animate-spin" aria-hidden="true"/> : <RefreshCw size={14} aria-hidden="true"/>}Refresh</Button></div>}
  {entry?.deliveries.error && <div className="requirements-error" role="alert"><AlertCircle size={16} aria-hidden="true"/><div><strong>Delivery blocked</strong><p>{entry.deliveries.error}</p></div></div>}
  <section className="delivery-section" aria-labelledby="delivery-prs-title">
   <div className="section-heading"><h2 id="delivery-prs-title">Pull requests</h2><span className="field-hint">{entry?.deliveries.data ? deliveries.length : "—"}</span></div>
   {deliveries.length ? <div className="delivery-cards">{deliveries.map(d => <EvidenceViewer key={d.run_id} delivery={d}/>)}</div> : <div className="workspace-empty"><GitPullRequest size={26} strokeWidth={1.4} aria-hidden="true"/><h3>No pull request yet</h3><p>A pull request appears here after a run passes independent evaluation and is delivered to GitHub.</p></div>}
  </section>
  <section className="delivery-section" aria-labelledby="delivery-trace-title">
   <div className="section-heading"><h2 id="delivery-trace-title">Traceability</h2><span className="field-hint">Requirement → task → run → evidence → PR</span></div>
   {entry?.runs.error && <p className="field-hint" role="status">{entry.runs.error}</p>}
   {tasks?.length ? <div className="task-table-wrap"><table className="task-table"><thead><tr><th>Requirement</th><th>Task</th><th>Latest run</th><th>Tests</th><th>Pull request</th></tr></thead><tbody>{tasks.map(t => { const run = latestRun(t.id), d = deliveryFor(t.id), state = prState(run, d); return <tr key={t.id}>
       <td>{t.requirement_ids.length ? t.requirement_ids.map(id => <Link key={id} href={requirementsHref} className="arch-chip">{id}</Link>) : <span className="field-hint">None</span>}</td>
       <td><Link href={planningHref} className="task-id">{t.id}</Link> <span className="field-hint">{t.title}</span></td>
       <td>{run ? <><code>{run.id}</code> <StatusBadge>{run.status}</StatusBadge></> : <span className="field-hint">Not run</span>}</td>
       <td className="font-mono">{d ? d.tests_passed : "—"}</td>
       <td>{d ? <a href={d.pr_url} target="_blank" rel="noopener noreferrer" className="task-id">#{d.pr_number}</a> : <span className="readiness" data-state={state === "error" ? "blocked" : undefined}>{state}</span>}</td>
      </tr>; })}</tbody></table></div> : <p className="field-hint">Load a plan in <Link href={planningHref} className="arch-link">Planning</Link> to trace tasks to runs and pull requests.</p>}
  </section>
  <section className="delivery-section" aria-labelledby="delivery-ac-title">
   <div className="section-heading"><h2 id="delivery-ac-title">Acceptance criteria matrix</h2></div>
   {acRows.length ? <div className="task-table-wrap"><table className="task-table"><thead><tr><th>Requirement</th><th>Acceptance criterion</th><th>Covering tasks</th><th>Status</th></tr></thead><tbody>{acRows.map(row => { const done = row.tasks.length > 0 && row.tasks.every(t => deliveryFor(t.id)); return <tr key={`${row.requirement}:${row.ac ?? "none"}`}>
       <td><Link href={requirementsHref} className="arch-chip">{row.requirement}</Link></td>
       <td>{row.ac ? <code>{row.ac}</code> : <span className="field-hint">No AC returned</span>}</td>
       <td>{row.tasks.length ? row.tasks.map(t => <code key={t.id} className="delivery-task-ref">{t.id}</code>) : <span className="field-hint">No task covers this</span>}</td>
       <td><span className="readiness" data-state={done ? "ready" : "blocked"}>{done ? "delivered" : row.tasks.length ? "unmet" : "uncovered"}</span></td>
      </tr>; })}</tbody></table></div> : <p className="field-hint">Open the requirements set in <Link href={requirementsHref} className="arch-link">Requirements</Link> to build the acceptance-criteria matrix.</p>}
  </section>
 </div>;
}
