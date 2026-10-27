"use client";
import { useEffect, useState } from "react";
import { ArrowRight, Check, FileText, LockKeyhole, Search, Sparkles, FolderOpen, LoaderCircle, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/shared/status-badge";
import { useRequirementsStore } from "@/stores/requirementsStore";
export function RequirementsWorkspace({ projectId }: {
    projectId: string;
}) {
    const entry = useRequirementsStore(s => s.entries[projectId]);
    const execute = useRequirementsStore(s => s.execute);
    const [brief, setBrief] = useState("");
    const [setId, setSetId] = useState("");
    const [reviewer, setReviewer] = useState("");
    const [search, setSearch] = useState("");
    const [selected, setSelected] = useState<string>();
    const [lockConfirmed, setLockConfirmed] = useState(false);
    const data = entry?.data;
    const pending = Boolean(entry?.pending);
    const preview = projectId === "preview";
    const blocked = pending || preview || entry?.uncertain;
    const locked = data?.set.status === "locked";
    const filtered = data?.requirements.filter(r => `${r.id} ${r.title} ${r.description}`.toLowerCase().includes(search.toLowerCase())) ?? [];
    const current = filtered.find(r => r.id === selected) ?? filtered[0];
    useEffect(() => {
        if (!brief.trim())
            return;
        const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [brief]);
    return <div className="workspace-page requirements-page">
  <div className="page-heading"><div><h1>Requirements</h1><p className="page-description">Turn engineering intent into a reviewed, versioned specification.</p></div><StatusBadge>{data ? data.set.status : "No set loaded"}</StatusBadge></div>
  <div className="workspace-tabs" aria-label="Requirements workflow"><a href="#engineering-brief" aria-current="page">Specification</a><a href="#requirement-detail-title">Review &amp; version lock</a></div>
  {preview && <p className="workspace-notice">Preview mode. Open a saved project to generate and review real requirements.</p>}
  <section className="intent-panel" aria-labelledby="intent-title">
   <div className="section-heading"><h2 id="intent-title">Engineering brief</h2><span className="field-hint">{brief.length.toLocaleString()} / 20,000</span></div>
   <form onSubmit={e => { e.preventDefault(); void execute(projectId, "analyze", brief.trim()); }}>
    <label htmlFor="engineering-brief" className="field-hint">Describe the change, expected behavior, and constraints.</label>
    <textarea id="engineering-brief" className="form-input brief-input" rows={4} maxLength={20000} value={brief} onChange={e => setBrief(e.target.value)} disabled={pending || preview || locked} placeholder="What should the software do, and how will we know it works?" required/>
    <div className="intent-footer"><p>Analysis creates a persisted draft for human review.</p><Button disabled={Boolean(blocked) || locked || !brief.trim()}>{entry?.pending === "analyze" ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <Sparkles size={15} aria-hidden="true"/>}{entry?.pending === "analyze" ? "Analyzing brief…" : "Analyze requirements"}</Button></div>
   </form>
  </section>
  <form className="open-set-bar" onSubmit={e => { e.preventDefault(); void execute(projectId, "read", (setId || data?.set.id || "").trim()); }}>
   <FolderOpen size={16} aria-hidden="true"/><label htmlFor="requirements-set-id">Open a saved set</label><Input id="requirements-set-id" value={setId || data?.set.id || ""} onChange={e => setSetId(e.target.value)} placeholder="RSET-001" pattern="RSET-[0-9]+" required disabled={pending || preview}/><Button variant="outline" disabled={pending || preview || !/^RSET-\d+$/.test((setId || data?.set.id || "").trim())}>Open set <ArrowRight size={14} aria-hidden="true"/></Button>
  </form>
  {entry?.error && <div className="requirements-error" role="alert"><AlertCircle size={16} aria-hidden="true"/><div><strong>{entry.uncertain ? "Result needs confirmation" : "Action could not be completed"}</strong><p>{entry.error}</p>{entry.uncertain && <p>Further writes are paused. Open the saved set above to reconcile its status. If analysis did not return an ID, ask the backend owner to check persisted records.</p>}</div></div>}
  <div className="requirements-grid">
   <section className="requirements-list-panel" aria-labelledby="requirements-list-title">
    <div className="section-heading"><h2 id="requirements-list-title">Requirements</h2><span className="field-hint">{data ? data.requirements.length : "—"}</span></div>
    <label className="requirement-search"><Search size={15} aria-hidden="true"/><Input aria-label="Search requirements" placeholder="Search requirements…" value={search} onChange={e => setSearch(e.target.value)}/></label>
    {filtered.length ? <ul className="requirement-list">{filtered.map(r => <li key={r.id}><button type="button" aria-pressed={current?.id === r.id} onClick={() => setSelected(r.id)}><span className="requirement-row-meta"><code>{r.id}</code><span>{r.priority}</span></span><strong>{r.title}</strong><span className="field-hint">{r.type} · v{r.version}</span></button></li>)}</ul> : <div className="workspace-empty"><FileText size={26} strokeWidth={1.4} aria-hidden="true"/><h3>{data ? "No matching requirements" : "Your specification starts here"}</h3><p>{data ? "Try another search." : "Analyze a brief or open a saved set to inspect its requirements."}</p></div>}
   </section>
   <section className="requirement-detail-panel" aria-labelledby="requirement-detail-title">
    <div className="section-heading"><h2 id="requirement-detail-title">{current ? "Requirement detail" : "Review specification"}</h2>{locked && <LockKeyhole size={16} aria-label="Locked version"/>}</div>
    {current ? <><div className="requirement-detail-meta"><code>{current.id}</code><span>Version {current.version}</span><StatusBadge>{current.status}</StatusBadge></div><h3 className="requirement-title">{current.title}</h3><p className="requirement-description">{current.description}</p><h4>Acceptance criteria references</h4><p className="field-hint">{current.trace.ac_ids.length ? current.trace.ac_ids.join(", ") : "No acceptance criteria references returned for this requirement."}</p></> : <div className="workspace-empty detail-empty"><h3>Review before execution</h3><p>Inspect the generated scope and assumptions, approve the specification, then lock its version.</p><ol><li>Generate a persisted draft</li><li>Review requirements and assumptions</li><li>Approve and lock the version</li></ol></div>}
    {data && <div className="set-review"><div className="requirement-detail-meta"><code>{data.set.id}</code><span>Version {data.set.version}</span></div><h4>Set summary</h4><p>{data.set.summary}</p><h4>Assumptions</h4>{data.set.assumptions.length ? <ul>{data.set.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul> : <p className="field-hint">No assumptions returned.</p>}<h4>Open questions</h4>{data.set.open_questions.length ? <ul>{data.set.open_questions.map((a, i) => <li key={i}>{a}</li>)}</ul> : <p className="field-hint">No open questions returned.</p>}
    {!locked && <div className="review-controls"><label htmlFor="reviewer-name">Reviewer name</label><Input id="reviewer-name" value={reviewer} onChange={e => setReviewer(e.target.value)} maxLength={200} placeholder="Your name" disabled={pending}/>{data.set.status === "approved" && <label className="form-checkbox"><input type="checkbox" checked={lockConfirmed} onChange={e => setLockConfirmed(e.target.checked)} disabled={pending}/>I reviewed this specification and want to freeze this version.</label>}<div className="state-actions"><Button disabled={Boolean(blocked) || !reviewer.trim() || !["draft", "in_review"].includes(data.set.status)} onClick={() => void execute(projectId, "approve", data.set.id, reviewer.trim())}><Check size={15} aria-hidden="true"/>Approve specification</Button><Button variant={data.set.status === "approved" ? "default" : "outline"} disabled={Boolean(blocked) || !reviewer.trim() || data.set.status !== "approved" || !lockConfirmed} onClick={() => void execute(projectId, "lock", data.set.id, reviewer.trim())}><LockKeyhole size={15} aria-hidden="true"/>Lock version</Button></div></div>}
    {locked && <p className="save-notice">This version is locked and read-only.</p>}</div>}
    <p className="contract-note">{locked ? "Amendment creation is awaiting backend support. Locked content cannot be edited here." : "Draft editing and amendment creation are awaiting backend support. Review the generated content before approval."}</p>
   </section>
  </div>
 </div>;
}
