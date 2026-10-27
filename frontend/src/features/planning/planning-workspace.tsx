"use client";
import { useEffect, useRef, useState } from "react";
import { recallArtifact } from "@/lib/recent-artifacts";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { planningService } from "@/services/planningService";
import { runsService } from "@/services/runsService";
import { AlertCircle, ArrowRight, Columns3, FolderOpen, ListChecks, LoaderCircle, Play, ShieldCheck, Sparkles, Table2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/shared/status-badge";
import { usePlanningStore } from "@/stores/planningStore";
import { useArchitectureStore } from "@/stores/architectureStore";
import { useRequirementsStore } from "@/stores/requirementsStore";
import type { PlanTask } from "@/lib/api/planning-contract";
const boardColumns = ["pending", "ready", "running", "done", "failed", "cancelled"];
function TaskRef({ id, onSelect, known }: {
    id: string;
    onSelect: (id: string) => void;
    known: boolean;
}) {
    return known ? <button type="button" className="arch-chip" onClick={() => onSelect(id)}>{id}</button> : <span className="arch-chip" title="Not part of this plan">{id}</span>;
}
export function PlanningWorkspace({ projectId }: {
    projectId: string;
}) {
    const entry = usePlanningStore(s => s.entries[projectId]);
    const decompose = usePlanningStore(s => s.decompose);
    const read = usePlanningStore(s => s.read);
    const checkReadiness = usePlanningStore(s => s.checkReadiness);
    const archId = useArchitectureStore(s => s.entries[projectId]?.data?.architecture.id);
    const lockedSet = useRequirementsStore(s => s.entries[projectId]?.data?.set);
    const [arch, setArch] = useState("");
    const [rsetInput, setRset] = useState("");
    const [context, setContext] = useState("");
    const [view, setView] = useState<"table" | "board">("table");
    const [selected, setSelected] = useState<string>();
    const data = entry?.data;
    const router = useRouter();
    const [starting, setStarting] = useState(false);
    const [startError, setStartError] = useState<string>();
    // Server-confirmed sequence: mark the task ready, create the run, execute it.
    const runTask = async (task: PlanTask) => {
        setStarting(true);
        setStartError(undefined);
        try {
            if (task.status === "pending")
                await planningService.markReady(projectId, task.id);
            const { run_id } = await runsService.start(projectId, task.id);
            await runsService.execute(projectId, run_id);
            router.push(`/projects/${projectId}/runs`);
        }
        catch (e) {
            setStartError(e instanceof Error ? e.message : "The run could not be started.");
            setStarting(false);
        }
    };
    const reopened = useRef(false);
    useEffect(() => {
        if (reopened.current || projectId === "preview" || data)
            return;
        reopened.current = true;
        const id = recallArtifact(projectId, "arch");
        if (!id)
            return;
        if (!archId)
            void useArchitectureStore.getState().read(projectId, id);
        void read(projectId, id);
    }, [archId, data, projectId, read]);
    const pending = Boolean(entry?.pending);
    const preview = projectId === "preview";
    const architectureId = (arch || archId || "").trim();
    const rset = (rsetInput || (lockedSet?.status === "locked" ? lockedSet.id : "")).trim();
    const tasks = data?.tasks ?? [];
    const ids = new Set(tasks.map(t => t.id));
    const current = tasks.find(t => t.id === selected);
    const readiness = current ? entry?.readiness[current.id] : undefined;
    const requirementsHref = `/projects/${projectId}/requirements`;
    const blockersOf = (t: PlanTask) => entry?.readiness[t.id]?.blocking_reasons ?? t.blocking_reasons;
    const readinessLabel = (t: PlanTask) => { const r = entry?.readiness[t.id]; return r?.pending ? "checking" : r?.error ? "unknown" : r?.readiness ?? t.readiness ?? "not checked"; };
    const row = (t: PlanTask) => <tr key={t.id} aria-selected={current?.id === t.id} onClick={() => setSelected(t.id)}>
   <td><button type="button" className="task-id" onClick={() => setSelected(t.id)}>{t.id}</button></td>
   <td className="task-title-cell"><strong>{t.title}</strong></td>
   <td><StatusBadge>{t.status}</StatusBadge></td>
   <td className="font-mono">{t.size.toUpperCase()}</td>
   <td>{t.ac_ids.length ? t.ac_ids.join(", ") : <span className="field-hint">None</span>}</td>
   <td className="font-mono">{t.depends_on.length}</td>
   <td><span className="readiness" data-state={readinessLabel(t)}>{readinessLabel(t)}</span></td>
   <td className="field-hint">Unassigned</td>
  </tr>;
    return <div className="workspace-page planning-page">
  <div className="page-heading"><div><h1>Planning</h1><p className="page-description">Inspect task dependencies, validation requirements and execution readiness.</p></div><StatusBadge>{data ? `${tasks.length} tasks` : "No plan loaded"}</StatusBadge></div>
  {preview && <p className="workspace-notice">Preview mode. Open a saved project to plan real tasks.</p>}
  <section className="intent-panel" aria-labelledby="plan-generate-title">
   <div className="section-heading"><h2 id="plan-generate-title">Decompose architecture into tasks</h2><span className="field-hint">{context.length.toLocaleString()} / 20,000</span></div>
   <form onSubmit={e => { e.preventDefault(); void decompose(projectId, architectureId, rset, context.trim()); }}>
    <div className="arch-generate-row"><label htmlFor="plan-arch" className="field-hint">Architecture</label><Input id="plan-arch" value={architectureId} onChange={e => setArch(e.target.value)} placeholder="ARCH-001" pattern="ARCH-[0-9]+" required disabled={pending || preview}/><label htmlFor="plan-rset" className="field-hint">Requirements set</label><Input id="plan-rset" value={rset} onChange={e => setRset(e.target.value)} placeholder="RSET-001 (optional)" pattern="RSET-[0-9]+" disabled={pending || preview}/></div>
    <label htmlFor="plan-context" className="field-hint">Optional planning context: sequencing constraints, team conventions.</label>
    <textarea id="plan-context" className="form-input brief-input" rows={2} maxLength={20000} value={context} onChange={e => setContext(e.target.value)} disabled={pending || preview}/>
    <div className="intent-footer"><p>Tasks are persisted with dependencies. Running them requires a readiness check.</p><Button disabled={pending || preview || entry?.uncertain || !/^ARCH-\d+$/.test(architectureId)}>{entry?.pending === "decompose" ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <Sparkles size={15} aria-hidden="true"/>}{entry?.pending === "decompose" ? "Planning tasks…" : "Decompose into tasks"}</Button></div>
   </form>
  </section>
  <form className="open-set-bar" onSubmit={e => { e.preventDefault(); void read(projectId, architectureId); }}>
   <FolderOpen size={16} aria-hidden="true"/><span>Load the saved plan for <code>{architectureId || "ARCH-…"}</code></span><Button variant="outline" disabled={pending || preview || !/^ARCH-\d+$/.test(architectureId)}>{entry?.pending === "read" ? <LoaderCircle size={14} className="animate-spin" aria-hidden="true"/> : null}Load plan <ArrowRight size={14} aria-hidden="true"/></Button>
  </form>
  {entry?.error && <div className="requirements-error" role="alert"><AlertCircle size={16} aria-hidden="true"/><div><strong>{entry.uncertain ? "Result needs confirmation" : "Action could not be completed"}</strong><p>{entry.error}</p>{entry.uncertain && <p>Decomposition is paused. Load the saved plan to confirm whether tasks were created.</p>}</div></div>}
  <div className="arch-grid plan-grid">
   <section className="arch-graph-panel" aria-labelledby="plan-tasks-title">
    <div className="section-heading arch-graph-heading"><h2 id="plan-tasks-title"><ListChecks size={15} aria-hidden="true"/>Tasks <span className="field-hint">{data ? tasks.length : "—"}</span></h2>
     <div className="segmented" role="group" aria-label="Task view"><button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}><Table2 size={14} aria-hidden="true"/>Table</button><button type="button" aria-pressed={view === "board"} onClick={() => setView("board")}><Columns3 size={14} aria-hidden="true"/>Board</button></div></div>
    {!tasks.length ? <div className="workspace-empty arch-empty"><ListChecks size={26} strokeWidth={1.4} aria-hidden="true"/><h3>{data ? "No tasks in this plan" : "Your execution plan starts here"}</h3><p>{data ? "Decompose the architecture to create tasks." : "Decompose an architecture into tasks, or load its saved plan."}</p></div>
            : view === "table" ? <div className="task-table-wrap"><table className="task-table"><thead><tr><th>ID</th><th>Task</th><th>Status</th><th>Size</th><th>Acceptance criteria</th><th>Deps</th><th>Readiness</th><th>Owner / agent</th></tr></thead><tbody>{tasks.map(row)}</tbody></table></div>
                : <div className="task-board">{boardColumns.filter(c => c !== "cancelled" || tasks.some(t => t.status === c)).map(c => <div key={c} className="task-board-column"><h3>{c} <span className="field-hint">{tasks.filter(t => t.status === c).length}</span></h3>{tasks.filter(t => t.status === c).map(t => <button key={t.id} type="button" className="task-card" aria-pressed={current?.id === t.id} onClick={() => setSelected(t.id)}><code>{t.id}</code><strong>{t.title}</strong><span className="field-hint">{t.depends_on.length} deps · {readinessLabel(t)}</span></button>)}</div>)}</div>}
   </section>
   <aside className="arch-inspector" aria-labelledby="task-inspector-title">
    <div className="arch-tabpanel">
     <h2 id="task-inspector-title" className="inspector-title">Task inspector</h2>
     {!current ? <p className="field-hint">{data ? "Select a task to inspect its contract, dependencies and blockers." : "Load a plan to inspect tasks."}</p> : <>
      <div className="requirement-detail-meta"><code>{current.id}</code><span>v{current.version}</span><StatusBadge>{current.status}</StatusBadge><span>Size {current.size.toUpperCase()}</span></div>
      <h3 className="requirement-title">{current.title}</h3><p className="requirement-description">{current.description}</p>
      <h4>Target paths</h4>{current.target_paths.length ? <ul className="task-paths">{current.target_paths.map(p => <li key={p}><code>{p}</code></li>)}</ul> : <p className="field-hint">No target paths declared.</p>}
      <h4>Requirements and acceptance criteria</h4>{current.requirement_ids.length + current.ac_ids.length ? <ul className="arch-chip-list">{[...current.requirement_ids, ...current.ac_ids].map(id => <li key={id}><Link href={requirementsHref} className="arch-chip">{id}</Link></li>)}</ul> : <p className="field-hint">No requirement or acceptance-criteria links returned.</p>}
      <h4>Prerequisites</h4>{current.depends_on.length ? <ul className="arch-chip-list">{current.depends_on.map(id => <li key={id}><TaskRef id={id} known={ids.has(id)} onSelect={setSelected}/></li>)}</ul> : <p className="field-hint">No prerequisite tasks.</p>}
      <h4>Blockers</h4>
      {readiness?.error ? <p className="field-hint" role="alert">{readiness.error}</p> : blockersOf(current).length ? <ul className="task-blockers">{blockersOf(current).map((reason, i) => { const ref = reason.match(/TASK-\d+/)?.[0]; return <li key={i}><AlertCircle size={13} aria-hidden="true"/><span>{reason}</span>{ref && <TaskRef id={ref} known={ids.has(ref)} onSelect={setSelected}/>}</li>; })}</ul> : <p className="field-hint">{readiness && !readiness.pending ? "No blockers reported." : "Readiness has not been checked."}</p>}
      <h4>Validation plan</h4><p className="field-hint">The task contract does not include a validation plan yet. Acceptance criteria above define what must pass.</p>
      {startError && <p className="field-hint" role="alert">{startError}</p>}
      <div className="state-actions task-actions">
       <Button variant="outline" disabled={preview || readiness?.pending} onClick={() => void checkReadiness(projectId, current.id)}>{readiness?.pending ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <ShieldCheck size={15} aria-hidden="true"/>}Check readiness</Button>
       {readiness?.readiness === "ready" && !readiness.pending && !readiness.error ? <Button disabled={starting} onClick={() => void runTask(current)}>{starting ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <Play size={15} aria-hidden="true"/>}{starting ? "Starting run…" : "Run task"}</Button> : <Button disabled title="Run is enabled after the backend confirms readiness"><Play size={15} aria-hidden="true"/>Run task</Button>}
      </div>
     </>}
    </div>
   </aside>
  </div>
 </div>;
}
