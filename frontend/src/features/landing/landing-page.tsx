"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowDown, ArrowRight, ArrowUpRight, CheckCircle2, CircleDashed, Github, Menu, Plus, Stethoscope, X, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { artifacts, links, stages } from "./scenario";
import styles from "./landing.module.css";

const TraceExplorer = dynamic(() => import("./trace-explorer"), {
  ssr: false,
  loading: () => <div className={styles.canvasLoading}>Loading the trace</div>,
});

const GITHUB_URL = "https://github.com/tekeufranck681/agentic-engineering-workspace";
const chain = ["INTENT", "REQ-014", "AC-031", "ADR-006", "TASK-053", "RUN-019 · 1", "PR #128"];
const chainLabel: Record<string, string> = { INTENT: "billing-service", "RUN-019 · 1": "RUN-019" };

const runSpecimen = [
  { seq: 4, phase: "Implementation", title: "Changed 2 files", detail: "billing/invoices/query.py, billing/invoices/export.py", tone: "neutral" },
  { seq: 5, phase: "Evaluation", title: "Evaluation failed on AC-031", detail: "February export included an invoice issued 1 Mar 00:30 local time.", tone: "fail" },
  { seq: 6, phase: "Diagnosis", title: "Month boundary used UTC", detail: "Correction: convert month bounds to the account time zone. Scope: query.py", tone: "warn" },
  { seq: 7, phase: "Implementation", title: "Changed 1 file", detail: "billing/invoices/query.py", tone: "neutral" },
  { seq: 8, phase: "Evaluation", title: "Independent evaluation passed", detail: "AC-031 pass, AC-032 pass. 14 tests passed.", tone: "pass" },
  { seq: 9, phase: "Delivery", title: "Pull request #128 opened", detail: "agent/run-019-task-053", tone: "pass" },
] as const;

const controls = [
  { title: "Lock the specification", text: "Requirements move from draft to approved to locked only when a named reviewer confirms it and the server agrees. Design starts from the locked version, never from a draft.", state: "draft → approved → locked" },
  { title: "Run only what is ready", text: "A task can run once every task it depends on is done. A blocked task names exactly what it is waiting for, so nobody has to guess.", state: "blocked: TASK-052 is pending" },
  { title: "Review the evidence, then merge", text: "The pull request carries its requirement, acceptance criteria, run and test results. Opening it is automatic. Merging stays with you.", state: "PR #128 · 14 tests passed" },
];

// Reveal-once on scroll, using the reference site's easing. Content is
// visible by default; the attribute only animates in when motion is allowed.
function useReveal() {
  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const els = document.querySelectorAll<HTMLElement>("[data-reveal]");
    els.forEach((el) => el.setAttribute("data-reveal", "pending"));
    const io = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.setAttribute("data-reveal", "shown"); io.unobserve(entry.target); }
    }), { rootMargin: "0px 0px -12% 0px" });
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
}

const ToneIcon = ({ tone }: { tone: string }) => tone === "pass" ? <CheckCircle2 size={14} aria-hidden="true" /> : tone === "fail" ? <XCircle size={14} aria-hidden="true" /> : tone === "warn" ? <Stethoscope size={14} aria-hidden="true" /> : <CircleDashed size={14} aria-hidden="true" />;

export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [stage, setStage] = useState(1);
  const [selected, setSelected] = useState("REQ-014");
  const [focus, setFocus] = useState<string[]>(stages[1].ids);
  useReveal();
  const artifact = artifacts.find((a) => a.id === selected) ?? artifacts[0];
  const connected = links.filter(([s, t]) => s === artifact.id || t === artifact.id).map(([s, t]) => (s === artifact.id ? t : s));

  const select = (id: string, refocus = false) => {
    setSelected(id);
    const owner = stages.findIndex((s) => s.ids.includes(id));
    if (owner >= 0) setStage(owner);
    if (refocus) setFocus([id, ...links.filter(([a, b]) => a === id || b === id).map(([a, b]) => (a === id ? b : a))]);
  };
  const chooseStage = (index: number) => {
    setStage(index);
    setSelected(stages[index].ids[0]);
    setFocus(stages[index].ids);
  };
  const jumpToTrace = (id: string) => {
    select(id, true);
    document.getElementById("trace")?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
  };

  return (
    <div className={styles.landing}>
      <a href="#landing-main" className="skip-link">Skip to content</a>
      <header className={styles.header} onKeyDown={(event) => {
        if (event.key === "Escape") { setMenuOpen(false); menuButton.current?.focus(); }
      }}>
        <div className={styles.navbar}>
          <Link className={styles.logo} href="/" aria-label="Engineering workspace home">
            <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><circle cx="5" cy="11" r="3" fill="currentColor" /><circle cx="17" cy="5" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><circle cx="17" cy="17" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" /><path d="M8 10.2 14.6 6M8 11.8l6.6 4.2" stroke="currentColor" strokeWidth="1.25" /></svg>
            <span>Engineering workspace</span>
          </Link>
          <nav className={styles.desktopNav} aria-label="Main navigation">
            <a href="#trace">Trace a change</a>
            <a href="#failure">When it fails</a>
            <a href="#control">Your controls</a>
            <a href={GITHUB_URL} target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={13} aria-hidden="true" /></a>
          </nav>
          <div className={styles.navActions}>
            <Button asChild size="sm" className={styles.navCta}><Link href="/projects">Open workspace <ArrowRight size={14} aria-hidden="true" /></Link></Button>
            <Button ref={menuButton} variant="ghost" size="icon" className={styles.menuToggle} aria-expanded={menuOpen} aria-controls="landing-mobile-nav" aria-label={menuOpen ? "Close menu" : "Open menu"} onClick={() => setMenuOpen(!menuOpen)}>
              {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
            </Button>
          </div>
        </div>
        {menuOpen && <nav id="landing-mobile-nav" className={styles.mobileNav} aria-label="Mobile navigation">
          {[["#trace", "Trace a change"], ["#failure", "When it fails"], ["#control", "Your controls"]].map(([href, label]) => <a key={href} href={href} onClick={() => setMenuOpen(false)}>{label} <ArrowDown size={14} aria-hidden="true" /></a>)}
          <a href={GITHUB_URL}>View on GitHub <ArrowUpRight size={14} aria-hidden="true" /></a>
          <Link href="/projects">Open workspace <ArrowRight size={14} aria-hidden="true" /></Link>
        </nav>}
      </header>

      <main id="landing-main">
        <section className={styles.hero} aria-labelledby="hero-title">
          <h1 id="hero-title">Every change,<br />accounted for.</h1>
          <div className={styles.heroAside}>
            <p>Describe a change to your repository. The workspace turns it into locked requirements, a design you can question, a plan with honest dependencies, an agent run you can audit, and a pull request that carries its own evidence.</p>
            <div className={styles.heroActions}>
              <Button asChild size="lg"><Link href="/projects/new"><Plus size={17} aria-hidden="true" />Create a project</Link></Button>
              <Button asChild variant="outline" size="lg"><a href="#trace">Trace a change <ArrowDown size={16} aria-hidden="true" /></a></Button>
            </div>
          </div>
          <div className={styles.record}>
            <ol className={styles.chain} aria-label="One change, from request to pull request (illustrative)">
              {chain.map((id, index) => {
                const a = artifacts.find((x) => x.id === id)!;
                return <li key={id} style={{ "--i": index } as React.CSSProperties}>
                  <button type="button" onClick={() => jumpToTrace(id)} data-tone={a.tone}>
                    <span className={styles.chainKind}>{a.label}</span>
                    <code>{chainLabel[id] ?? id}</code>
                    <span className={styles.chainTitle}>{a.title}</span>
                  </button>
                </li>;
              })}
            </ol>
            <p className={styles.caption}>Illustrative workflow. Every artifact keeps a stable ID from request to pull request. Select one to trace it.</p>
          </div>
        </section>

        <section id="trace" className={styles.trace} aria-labelledby="trace-title">
          <div className={styles.sectionHead} data-reveal>
            <h2 id="trace-title">Follow one change from request to pull request.</h2>
            <p>Select any artifact to see its lineage: what it came from, what it produced, and the evidence in between. Nothing here is decoration. Each line is a link the workspace keeps.</p>
          </div>
          <div className={styles.stageRail} role="tablist" aria-label="Lifecycle stage">
            {stages.map((s, index) => <button key={s.label} type="button" role="tab" aria-selected={stage === index} onClick={() => chooseStage(index)}>{s.label}</button>)}
          </div>
          <p className={styles.stageNote}>{stages[stage].note}</p>
          <div className={styles.explorer}>
            <div className={styles.graph} role="group" aria-label="Trace graph. The same artifacts are listed in the panel beside it.">
              <TraceExplorer selected={selected} focus={focus} onSelect={(id) => select(id)} />
            </div>
            <aside className={styles.inspector} aria-live="polite" aria-label="Selected artifact">
              <div className={styles.inspectorHead}><span>{artifact.label}</span><code data-tone={artifact.tone}>{artifact.id}</code></div>
              <h3>{artifact.title}</h3>
              <p>{artifact.body}</p>
              <dl>{artifact.fields.map(([k, v]) => <div key={k}><dt>{k}</dt><dd data-verdict={v === "PASS" || v === "FAIL" ? v : undefined}>{v}</dd></div>)}</dl>
              <h4>Linked to</h4>
              <ul className={styles.linked}>{connected.map((id) => <li key={id}><button type="button" onClick={() => select(id, true)}>{id}</button></li>)}</ul>
              <div className={styles.stageList} aria-label={`${stages[stage].label} artifacts`}>
                {stages[stage].ids.map((id) => <button key={id} type="button" aria-pressed={selected === id} onClick={() => select(id, true)}><code>{id}</code>{artifacts.find((a) => a.id === id)?.title}</button>)}
              </div>
              <p className={styles.caption}>Illustrative workflow</p>
            </aside>
          </div>
        </section>

        <section id="failure" className={styles.failure} aria-labelledby="failure-title">
          <div className={styles.failureCopy} data-reveal>
            <h2 id="failure-title">Failure stays on the record.</h2>
            <p>When independent evaluation rejects an acceptance criterion, the run does not smooth it over. The failing criterion, the diagnosis and the narrowed correction are persisted in order, and the change is evaluated again before anything reaches GitHub.</p>
            <p>Implementation finishing is not the same as passing. The workspace keeps those two things apart.</p>
            <Link href="/projects" className={styles.textLink}>See it in Agent Runs <ArrowRight size={14} aria-hidden="true" /></Link>
          </div>
          <figure className={styles.runSpecimen} data-reveal>
            <figcaption><code>RUN-019</code><span>Task TASK-053 · 2 attempts</span><span className={styles.illustrative}>Illustrative</span></figcaption>
            <ol>{runSpecimen.map((e) => <li key={e.seq} data-tone={e.tone}>
              <span className={styles.seq}>{e.seq}</span>
              <span className={styles.node}><ToneIcon tone={e.tone} /></span>
              <span className={styles.eventText}><span>{e.phase}</span><strong>{e.title}</strong><small>{e.detail}</small></span>
            </li>)}</ol>
          </figure>
        </section>

        <section id="control" className={styles.control} aria-labelledby="control-title">
          <h2 id="control-title" data-reveal>Three places where a person decides.</h2>
          <ul>{controls.map((c) => <li key={c.title} data-reveal>
            <h3>{c.title}</h3>
            <p>{c.text}</p>
            <code>{c.state}</code>
          </li>)}</ul>
        </section>

        <section className={styles.start} aria-labelledby="start-title">
          <h2 id="start-title">Start with the change you want to make.</h2>
          <div className={styles.heroActions}>
            <Button asChild size="lg"><Link href="/projects/new"><Plus size={17} aria-hidden="true" />Create a project</Link></Button>
            <Button asChild variant="outline" size="lg"><Link href="/projects">Open the workspace <ArrowRight size={16} aria-hidden="true" /></Link></Button>
          </div>
        </section>
      </main>
      <footer className={styles.footer}>
        <span className={styles.footerBrand}>Engineering workspace</span>
        <span>Requirements through evidenced delivery.</span>
        <a href={GITHUB_URL} aria-label="Engineering workspace on GitHub"><Github size={18} aria-hidden="true" /></a>
      </footer>
    </div>
  );
}
