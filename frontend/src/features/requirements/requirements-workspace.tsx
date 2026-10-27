"use client";
import { useEffect, useRef, useState } from "react";
import { recallArtifact } from "@/lib/recent-artifacts";
import { AlertCircle, ArrowRight, Check, FolderOpen, LoaderCircle, LockKeyhole, Search, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRequirementsStore } from "@/stores/requirementsStore";
import styles from "./requirements.module.css";
// The set's real lifecycle. A step is only marked reached from server state.
const lifecycle = [
    { key: "draft", label: "Draft" },
    { key: "approved", label: "Approved" },
    { key: "locked", label: "Locked" },
] as const;
const reached = (status: string) => status === "locked" ? 2 : status === "approved" ? 1 : 0;
const prompts = [
    ["What should change", "The behavior you want, in plain words."],
    ["Who it is for", "The people or systems affected."],
    ["How we will know", "Observable outcomes a test could check."],
    ["What must not change", "Constraints, existing behavior, limits."],
];
export function RequirementsWorkspace({ projectId }: {
    projectId: string;
}) {
    const entry = useRequirementsStore(s => s.entries[projectId]);
    const execute = useRequirementsStore(s => s.execute);
    const criteriaEntry = useRequirementsStore(s => s.criteria[projectId]);
    const loadCriteria = useRequirementsStore(s => s.loadCriteria);
    const [brief, setBrief] = useState("");
    const [setId, setSetId] = useState("");
    const [reviewer, setReviewer] = useState("");
    const [search, setSearch] = useState("");
    const [lockConfirmed, setLockConfirmed] = useState(false);
    const [composing, setComposing] = useState(false);
    const data = entry?.data;
    const pending = Boolean(entry?.pending);
    const preview = projectId === "preview";
    const blocked = pending || preview || entry?.uncertain;
    const locked = data?.set.status === "locked";
    const filtered = data?.requirements.filter(r => `${r.id} ${r.title} ${r.description}`.toLowerCase().includes(search.toLowerCase())) ?? [];
    const showComposer = !data || composing;
    const loadedSetId = entry?.data?.set.id;
    useEffect(() => {
        if (loadedSetId && projectId !== "preview")
            void loadCriteria(projectId, loadedSetId);
    }, [loadCriteria, loadedSetId, projectId]);
    // Reopen the last saved set from the backend after a reload.
    const reopened = useRef(false);
    useEffect(() => {
        if (reopened.current || preview || data)
            return;
        reopened.current = true;
        const id = recallArtifact(projectId, "rset");
        if (id)
            void execute(projectId, "read", id);
    }, [data, execute, preview, projectId]);
    useEffect(() => {
        if (!brief.trim())
            return;
        const warn = (e: BeforeUnloadEvent) => { e.preventDefault(); };
        window.addEventListener("beforeunload", warn);
        return () => window.removeEventListener("beforeunload", warn);
    }, [brief]);
    const openSet = <form className={styles.openSet} onSubmit={e => { e.preventDefault(); void execute(projectId, "read", (setId || data?.set.id || "").trim()); }}>
   <FolderOpen size={15} aria-hidden="true"/><label htmlFor="requirements-set-id">Open a saved set</label>
   <Input id="requirements-set-id" value={setId || data?.set.id || ""} onChange={e => setSetId(e.target.value)} placeholder="RSET-001" pattern="RSET-[0-9]+" required disabled={pending || preview}/>
   <Button variant="outline" size="sm" disabled={pending || preview || !/^RSET-\d+$/.test((setId || data?.set.id || "").trim())}>{entry?.pending === "read" ? <LoaderCircle size={13} className="animate-spin" aria-hidden="true"/> : null}Open <ArrowRight size={13} aria-hidden="true"/></Button>
  </form>;
    return <div className={`workspace-page ${styles.page}`}>
  <header className={styles.header}>
   <div>
    <h1>Requirements</h1>
    <p>Agree on what the change must do before anything is designed or built.</p>
   </div>
   {data && <ol className={styles.lifecycle} aria-label="Specification lifecycle">{lifecycle.map((step, i) => <li key={step.key} data-reached={i <= reached(data.set.status) || undefined} aria-current={i === reached(data.set.status) ? "step" : undefined}><span className={styles.tick}>{i < reached(data.set.status) || (locked && i === 2) ? <Check size={11} aria-hidden="true"/> : i + 1}</span>{step.label}</li>)}</ol>}
  </header>
  {preview && <p className="workspace-notice">Preview mode. Open a saved project to write and review a real specification.</p>}
  {entry?.error && <div className="requirements-error" role="alert"><AlertCircle size={16} aria-hidden="true"/><div><strong>{entry.uncertain ? "Result needs confirmation" : "Action could not be completed"}</strong><p>{entry.error}</p>{entry.uncertain && <p>Further writes are paused. Open the saved set to reconcile its status. If analysis did not return an ID, ask the backend owner to check persisted records.</p>}</div></div>}

  {showComposer ? <section className={styles.composer} aria-labelledby="brief-title">
    <div className={styles.composerMain}>
     <div className={styles.composerHead}><h2 id="brief-title">Engineering brief</h2><span>{brief.length.toLocaleString()} / 20,000</span></div>
     <form onSubmit={e => { e.preventDefault(); void execute(projectId, "analyze", brief.trim()); setComposing(false); }}>
      <label htmlFor="engineering-brief" className="sr-only">Describe the change</label>
      <textarea id="engineering-brief" className={styles.brief} rows={9} maxLength={20000} value={brief} onChange={e => setBrief(e.target.value)} disabled={pending || preview} placeholder="Billing admins need to export every invoice issued in a chosen month as CSV, using the account's time zone. Existing invoice issuing must not change." required/>
      <div className={styles.composerFoot}>
       <p>Analysis creates a persisted draft. Nothing is approved until a named reviewer approves it.</p>
       <div className={styles.composerActions}>
        {data && <Button type="button" variant="ghost" onClick={() => setComposing(false)}>Back to {data.set.id}</Button>}
        <Button disabled={Boolean(blocked) || !brief.trim()}>{entry?.pending === "analyze" ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <Sparkles size={15} aria-hidden="true"/>}{entry?.pending === "analyze" ? "Analyzing brief…" : "Analyze into requirements"}</Button>
       </div>
      </div>
     </form>
    </div>
    <aside className={styles.guide} aria-label="What a good brief covers">
     <h3>A good brief covers</h3>
     <dl>{prompts.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
     {openSet}
    </aside>
   </section>
            : data && <div className={styles.spec}>
    <nav className={styles.index} aria-label="Requirements index">
     <label className={styles.search}><Search size={14} aria-hidden="true"/><Input aria-label="Search requirements" placeholder="Search" value={search} onChange={e => setSearch(e.target.value)}/></label>
     {filtered.length ? <ol>{filtered.map(r => <li key={r.id}><a href={`#${r.id}`}><code>{r.id}</code><span>{r.title}</span></a></li>)}</ol> : <p className={styles.muted}>No requirement matches “{search}”.</p>}
     <div className={styles.indexFoot}>{openSet}{!locked && <Button variant="ghost" size="sm" onClick={() => setComposing(true)} disabled={preview}>New analysis</Button>}</div>
    </nav>

    <article className={styles.document} aria-labelledby="spec-title">
     <div className={styles.docMeta}><code>{data.set.id}</code><span>Version {data.set.version}</span><span>{data.requirements.length} requirement{data.requirements.length === 1 ? "" : "s"}</span>{locked && <span className={styles.lockedTag}><LockKeyhole size={12} aria-hidden="true"/>Read only</span>}</div>
     <h2 id="spec-title">Specification</h2>
     <p className={styles.summary}>{data.set.summary}</p>
     {data.requirements.map(r => <section key={r.id} id={r.id} className={styles.requirement} aria-labelledby={`${r.id}-title`}>
       <div className={styles.reqMeta}><code>{r.id}</code><span>{r.type}</span><span>Priority {r.priority}</span><span>v{r.version}</span></div>
       <h3 id={`${r.id}-title`}>{r.title}</h3>
       <p>{r.description}</p>
       {(criteriaEntry?.data ?? []).some(a => a.requirement_id === r.id)
                ? <ol className={styles.criteria}>{(criteriaEntry?.data ?? []).filter(a => a.requirement_id === r.id).map(a => <li key={a.id}>
           <div className={styles.criterionHead}><code>{a.id}</code><strong>{a.title}</strong>{a.verification && <span>{a.verification}</span>}</div>
           <dl><div><dt>Given</dt><dd>{a.given.join("; ")}</dd></div><div><dt>When</dt><dd>{a.when.join("; ")}</dd></div><div><dt>Then</dt><dd>{a.then.join("; ")}</dd></div></dl>
          </li>)}</ol>
                : <div className={styles.acRow}><span>Acceptance criteria</span>{r.trace.ac_ids.length ? r.trace.ac_ids.map(id => <code key={id}>{id}</code>) : <em>None yet. Generate them from the review panel.</em>}</div>}
      </section>)}
     <p className={styles.contractNote}>{locked ? "Amendment creation is awaiting backend support. Locked content cannot be edited here." : "Draft editing is awaiting backend support. Review the generated content before approval."}</p>
    </article>

    <aside className={styles.review} aria-labelledby="review-title">
     <h2 id="review-title">Review</h2>
     {locked ? <div className={styles.lockedState}><LockKeyhole size={16} aria-hidden="true"/><div><strong>Version {data.set.version} is locked</strong><p>Design and planning start from this version. It can no longer change.</p></div></div>
                : <div className={styles.reviewControls}>
       <p className={styles.nextStep}>{data.set.status === "approved" ? "Approved. Lock this version to freeze the scope design will build on." : "Read every requirement and its assumptions, then approve the specification."}</p>
       <label htmlFor="reviewer-name">Reviewer name</label>
       <Input id="reviewer-name" value={reviewer} onChange={e => setReviewer(e.target.value)} maxLength={200} placeholder="Your name" disabled={pending}/>
       {data.set.status === "approved" ? <>
         <label className={styles.confirm}><input type="checkbox" checked={lockConfirmed} onChange={e => setLockConfirmed(e.target.checked)} disabled={pending}/>I reviewed this specification and want to freeze version {data.set.version}.</label>
         <Button disabled={Boolean(blocked) || !reviewer.trim() || !lockConfirmed} onClick={() => void execute(projectId, "lock", data.set.id, reviewer.trim())}>{entry?.pending === "lock" ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <LockKeyhole size={15} aria-hidden="true"/>}Lock version {data.set.version}</Button>
        </> : <Button disabled={Boolean(blocked) || !reviewer.trim() || !["draft", "in_review"].includes(data.set.status)} onClick={() => void execute(projectId, "approve", data.set.id, reviewer.trim())}>{entry?.pending === "approve" ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <Check size={15} aria-hidden="true"/>}Approve specification</Button>}
      </div>}
     <h3>Acceptance criteria</h3>
     <p className={styles.criteriaNote}>{criteriaEntry?.data?.length ? `${criteriaEntry.data.length} testable criteria. Evaluation checks every task against them.` : "Runs need testable criteria to evaluate. Generate them for every requirement in this set."}</p>
     {criteriaEntry?.error && <p className={styles.criteriaError} role="alert">{criteriaEntry.error}</p>}
     <Button variant={criteriaEntry?.data?.length ? "outline" : "default"} disabled={preview || Boolean(criteriaEntry?.pending)} onClick={() => void loadCriteria(projectId, data.set.id, true)}>{criteriaEntry?.pending === "generate" ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <Sparkles size={15} aria-hidden="true"/>}{criteriaEntry?.pending === "generate" ? "Generating criteria…" : criteriaEntry?.data?.length ? "Generate more criteria" : "Generate acceptance criteria"}</Button>
     <h3>Assumptions</h3>
     {data.set.assumptions.length ? <ul>{data.set.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul> : <p className={styles.muted}>None returned.</p>}
     <h3>Open questions</h3>
     {data.set.open_questions.length ? <ul className={styles.questions}>{data.set.open_questions.map((a, i) => <li key={i}>{a}</li>)}</ul> : <p className={styles.muted}>None returned.</p>}
    </aside>
   </div>}
 </div>;
}
