"use client";
import { useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, Boxes, FileCode2, FolderOpen, LayoutList, ListChecks, LoaderCircle, Network, ScrollText, Sparkles, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/shared/status-badge";
import { ArchitectureGraph } from "@/components/graphs/architecture-graph";
import { useArchitectureStore } from "@/stores/architectureStore";
import { useRequirementsStore } from "@/stores/requirementsStore";
const tabs = [
    { key: "component", label: "Component", icon: Boxes },
    { key: "decisions", label: "Decisions", icon: ScrollText },
    { key: "contracts", label: "Contracts", icon: FileCode2 },
    { key: "validation", label: "Validation plan", icon: ListChecks },
] as const;
type Tab = (typeof tabs)[number]["key"];
export function ArchitectureWorkspace({ projectId }: {
    projectId: string;
}) {
    const entry = useArchitectureStore(s => s.entries[projectId]);
    const generate = useArchitectureStore(s => s.generate);
    const read = useArchitectureStore(s => s.read);
    const lockedSet = useRequirementsStore(s => s.entries[projectId]?.data?.set);
    const [setId, setSetId] = useState("");
    const [context, setContext] = useState("");
    const [archId, setArchId] = useState("");
    const [view, setView] = useState<"canvas" | "list">("canvas");
    const [tab, setTab] = useState<Tab>("component");
    const [selected, setSelected] = useState<string>();
    const data = entry?.data;
    const pending = Boolean(entry?.pending);
    const preview = projectId === "preview";
    const rset = setId || (lockedSet?.status === "locked" ? lockedSet.id : "");
    const openId = archId || data?.architecture.id || "";
    const components = data?.architecture.components ?? [];
    const current = components.find(c => c.name === selected) ?? components[0];
    const requirementsHref = `/projects/${projectId}/requirements`;
    return <div className="workspace-page architecture-page">
  <div className="page-heading"><div><h1>Architecture</h1><p className="page-description">Design components, decisions and contracts from a locked specification.</p></div><StatusBadge>{data ? data.architecture.status : "No architecture loaded"}</StatusBadge></div>
  {preview && <p className="workspace-notice">Preview mode. Open a saved project to generate and inspect a real architecture.</p>}
  <section className="intent-panel" aria-labelledby="arch-generate-title">
   <div className="section-heading"><h2 id="arch-generate-title">Generate from requirements</h2><span className="field-hint">{context.length.toLocaleString()} / 20,000</span></div>
   <form onSubmit={e => { e.preventDefault(); void generate(projectId, rset.trim(), context.trim()); }}>
    <div className="arch-generate-row"><label htmlFor="arch-rset" className="field-hint">Locked requirements set</label><Input id="arch-rset" value={rset} onChange={e => setSetId(e.target.value)} placeholder="RSET-001" pattern="RSET-[0-9]+" required disabled={pending || preview}/></div>
    <label htmlFor="arch-context" className="field-hint">Optional design context: constraints, existing systems, preferred technologies.</label>
    <textarea id="arch-context" className="form-input brief-input" rows={3} maxLength={20000} value={context} onChange={e => setContext(e.target.value)} disabled={pending || preview} placeholder="e.g. Reuse the existing PostgreSQL instance; expose a REST API."/>
    <div className="intent-footer"><p>Only a locked requirements set can be designed. The result is persisted as a draft.</p><Button disabled={pending || preview || entry?.uncertain || !/^RSET-\d+$/.test(rset.trim())}>{entry?.pending === "generate" ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true"/> : <Sparkles size={15} aria-hidden="true"/>}{entry?.pending === "generate" ? "Designing architecture…" : "Generate architecture"}</Button></div>
   </form>
  </section>
  <form className="open-set-bar" onSubmit={e => { e.preventDefault(); void read(projectId, openId.trim()); }}>
   <FolderOpen size={16} aria-hidden="true"/><label htmlFor="arch-id">Open a saved architecture</label><Input id="arch-id" value={openId} onChange={e => setArchId(e.target.value)} placeholder="ARCH-001" pattern="ARCH-[0-9]+" required disabled={pending || preview}/><Button variant="outline" disabled={pending || preview || !/^ARCH-\d+$/.test(openId.trim())}>{entry?.pending === "read" ? <LoaderCircle size={14} className="animate-spin" aria-hidden="true"/> : null}Open architecture <ArrowRight size={14} aria-hidden="true"/></Button>
  </form>
  {entry?.error && <div className="requirements-error" role="alert"><AlertCircle size={16} aria-hidden="true"/><div><strong>{entry.uncertain ? "Result needs confirmation" : "Action could not be completed"}</strong><p>{entry.error}</p>{entry.uncertain && <p>Generation is paused. Open the saved architecture above to confirm whether a draft was created.</p>}</div></div>}
  {data && <div className="arch-summary"><div className="requirement-detail-meta"><code>{data.architecture.id}</code><span>Version {data.architecture.version}</span>{data.architecture.derived_from.map(id => <Link key={id} href={requirementsHref} className="arch-link">from {id}</Link>)}</div><p>{data.architecture.summary}</p></div>}
  <div className="arch-grid">
   <section className="arch-graph-panel" aria-labelledby="arch-graph-title">
    <div className="section-heading arch-graph-heading"><h2 id="arch-graph-title"><Network size={15} aria-hidden="true"/>Components <span className="field-hint">{data ? components.length : "—"}</span></h2>
     <div className="segmented" role="group" aria-label="Component view"><button type="button" aria-pressed={view === "canvas"} onClick={() => setView("canvas")}><Workflow size={14} aria-hidden="true"/>Canvas</button><button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}><LayoutList size={14} aria-hidden="true"/>List</button></div></div>
    {!components.length ? <div className="workspace-empty arch-empty"><Network size={26} strokeWidth={1.4} aria-hidden="true"/><h3>{data ? "No components returned" : "Your system design starts here"}</h3><p>{data ? "This architecture has no components. Regenerate it with more design context." : "Generate an architecture from a locked requirements set, or open a saved one."}</p></div>
            : view === "canvas" ? <ArchitectureGraph components={components} selected={current?.name} onSelect={name => { setSelected(name); setTab("component"); }}/>
                : <ul className="requirement-list arch-component-list">{components.map(c => <li key={c.name}><button type="button" aria-pressed={current?.name === c.name} onClick={() => { setSelected(c.name); setTab("component"); }}><strong>{c.name}</strong><span className="field-hint">{c.responsibility}</span><span className="field-hint">{c.depends_on.length ? `Depends on ${c.depends_on.join(", ")}` : "No dependencies"}</span></button></li>)}</ul>}
   </section>
   <aside className="arch-inspector" aria-labelledby="arch-inspector-title">
    <h2 id="arch-inspector-title" className="sr-only">Architecture inspector</h2>
    <div className="workspace-tabs arch-tabs" role="tablist" aria-label="Inspector">{tabs.map(t => <button key={t.key} type="button" role="tab" id={`arch-tab-${t.key}`} aria-selected={tab === t.key} aria-controls="arch-tabpanel" onClick={() => setTab(t.key)}><t.icon size={13} aria-hidden="true"/>{t.label}</button>)}</div>
    <div id="arch-tabpanel" role="tabpanel" aria-labelledby={`arch-tab-${tab}`} className="arch-tabpanel">
     {!data ? <p className="field-hint">Select a component after loading an architecture to inspect its requirements, decisions and contracts.</p>
            : tab === "component" ? (current ? <>
       <h3 className="requirement-title">{current.name}</h3><p className="requirement-description">{current.responsibility}</p>
       <h4>Linked requirements</h4>{current.requirement_ids.length ? <ul className="arch-chip-list">{current.requirement_ids.map(id => <li key={id}><Link href={requirementsHref} className="arch-chip">{id}</Link></li>)}</ul> : <p className="field-hint">No requirements are linked to this component.</p>}
       <h4>Depends on</h4>{current.depends_on.length ? <ul className="arch-chip-list">{current.depends_on.map(name => <li key={name}>{components.some(c => c.name === name) ? <button type="button" className="arch-chip" onClick={() => setSelected(name)}>{name}</button> : <span className="arch-chip" title="Not a component in this architecture">{name}</span>}</li>)}</ul> : <p className="field-hint">No dependencies.</p>}
       <h4>Used by</h4>{components.some(c => c.depends_on.includes(current.name)) ? <ul className="arch-chip-list">{components.filter(c => c.depends_on.includes(current.name)).map(c => <li key={c.name}><button type="button" className="arch-chip" onClick={() => setSelected(c.name)}>{c.name}</button></li>)}</ul> : <p className="field-hint">No component depends on this one.</p>}
      </> : <p className="field-hint">No component selected.</p>)
                : tab === "decisions" ? (data.decisions.length ? <ul className="arch-decisions">{data.decisions.map(d => <li key={d.id}><div className="requirement-detail-meta"><code>{d.id}</code><span>v{d.version}</span><StatusBadge>{d.status}</StatusBadge></div><h3>{d.title}</h3><h4>Context</h4><p>{d.context}</p><h4>Decision</h4><p>{d.decision}</p>{d.alternatives.length > 0 && <><h4>Alternatives considered</h4><ul>{d.alternatives.map((a, i) => <li key={i}>{a}</li>)}</ul></>}{d.consequences.length > 0 && <><h4>Consequences</h4><ul>{d.consequences.map((a, i) => <li key={i}>{a}</li>)}</ul></>}</li>)}</ul> : <p className="field-hint">No architecture decision records were returned for {data.architecture.id}.</p>)
                    : tab === "contracts" ? (data.contracts.length ? <ul className="arch-decisions">{data.contracts.map(c => <li key={c.id}><div className="requirement-detail-meta"><code>{c.id}</code><span>v{c.version}</span><StatusBadge>{c.status}</StatusBadge></div><p>{c.summary}</p></li>)}</ul> : <p className="field-hint">No engineering contracts are linked to this architecture yet. The architecture API does not currently return linked contracts.</p>)
                        : <p className="field-hint">The architecture contract does not include a validation plan. Validation requirements are defined per task in Planning.</p>}
    </div>
   </aside>
  </div>
 </div>;
}
