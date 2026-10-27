"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowDown, ArrowRight, ArrowUpRight, Check, ChevronRight, Code2,
  FileCode2, FileText, GitBranch, GitPullRequest, Github,
  Layers3, ListChecks, LockKeyhole, Menu, Plus, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import styles from "./landing.module.css";

const example = [
  {
    label: "Requirement", id: "REQ-001", icon: FileText,
    title: "Export monthly invoices",
    description: "Let a billing administrator download invoices for a selected month as a CSV file.",
    rows: [
      ["Scope", "Billing · Invoice export"],
      ["Acceptance", "Only invoices from the selected month"],
      ["Constraint", "Keep existing billing behavior unchanged"],
    ],
    footer: "A clear outcome before implementation begins.",
  },
  {
    label: "Acceptance", id: "AC-001", icon: ListChecks,
    title: "Make the outcome testable",
    description: "Given invoices from different months, when March is selected, the export includes only March invoices.",
    rows: [
      ["Requirement", "REQ-001 · Export monthly invoices"],
      ["Verification", "An automated test of the exported rows"],
      ["Review", "Check the criterion before locking scope"],
    ],
    footer: "A requirement with a concrete way to verify it.",
  },
  {
    label: "Traceability", id: "REQ-001 → AC-001", icon: GitBranch,
    title: "Keep the reason with the change",
    description: "Connect the original requirement to its acceptance criterion, implementation task, and review evidence.",
    rows: [
      ["Intent", "Export monthly invoices"],
      ["Change", "The scoped implementation task"],
      ["Evidence", "Test results attached for review"],
    ],
    footer: "An inspectable path from the brief to delivery.",
  },
];

const workflow = [
  { number: "01", title: "Define the change", icon: FileText, text: "Start with a brief. Review requirements, assumptions, and acceptance criteria before locking the scope.", workspaces: "Overview / Requirements" },
  { number: "02", title: "Make the plan reviewable", icon: Layers3, text: "Connect architecture decisions to engineering contracts and tasks with explicit dependencies.", workspaces: "Architecture / Planning" },
  { number: "03", title: "Follow the work to delivery", icon: GitPullRequest, text: "Bring execution, evaluation, and change evidence into the same project context for human review.", workspaces: "Agent Runs / Delivery" },
];

export function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [active, setActive] = useState(0);
  const item = example[active];
  const Icon = item.icon;
  return (
    <div className={styles.landing}>
      <a href="#landing-main" className="skip-link">Skip to content</a>
      <header className={styles.header} onKeyDown={(event) => {
        if (event.key === "Escape") { setMenuOpen(false); menuButton.current?.focus(); }
      }}>
        <div className={styles.navbar}>
          <Link className={styles.logo} href="/" aria-label="Engineering workspace home">
            <Code2 size={25} strokeWidth={1.7} aria-hidden="true" />
            <span>Engineering<span className={styles.logoSuffix}> workspace</span></span>
          </Link>
          <nav className={styles.desktopNav} aria-label="Main navigation">
            <a href="#workflow">Workflow</a>
            <a href="#principles">Why this workspace</a>
            <a href="https://github.com/tekeufranck681/agentic-engineering-workspace" target="_blank" rel="noreferrer">GitHub <ArrowUpRight size={13} aria-hidden="true" /></a>
          </nav>
          <div className={styles.navActions}>
            <Button asChild size="sm"><Link href="/projects">Open workspace <ArrowRight size={14} aria-hidden="true" /></Link></Button>
            <Button ref={menuButton} variant="ghost" size="icon" className={styles.menuToggle} aria-expanded={menuOpen} aria-controls="landing-mobile-nav" aria-label={menuOpen ? "Close menu" : "Open menu"} onClick={() => setMenuOpen(!menuOpen)}>
              {menuOpen ? <X size={18} aria-hidden="true" /> : <Menu size={18} aria-hidden="true" />}
            </Button>
          </div>
        </div>
        {menuOpen && <nav id="landing-mobile-nav" className={styles.mobileNav} aria-label="Mobile navigation">
          <a href="#workflow" onClick={() => setMenuOpen(false)}>Workflow <ArrowDown size={14} aria-hidden="true" /></a>
          <a href="#principles" onClick={() => setMenuOpen(false)}>Why this workspace <ArrowDown size={14} aria-hidden="true" /></a>
          <a href="https://github.com/tekeufranck681/agentic-engineering-workspace">View on GitHub <ArrowUpRight size={14} aria-hidden="true" /></a>
        </nav>}
      </header>

      <main id="landing-main">
        <section className={styles.hero} aria-labelledby="hero-title">
          <div className={styles.heroCopy}>
            <h1 id="hero-title">From intent<br />to <span>evidence.</span></h1>
            <p className={styles.heroDescription}>A shared workspace for engineering with AI. Give every change a clear requirement, a reviewable plan, and a trail back to the why.</p>
            <div className={styles.heroActions}>
              <Button asChild size="lg"><Link href="/projects/new"><Plus size={17} aria-hidden="true" /> Create a project</Link></Button>
              <Button asChild variant="outline" size="lg"><Link href="/projects/preview/requirements">Explore the workspace <ArrowUpRight size={16} aria-hidden="true" /></Link></Button>
            </div>
            <p className={styles.heroNote}><Code2 size={14} aria-hidden="true" /> Built for the engineering work around the code.</p>
          </div>

          <div className={styles.example} aria-label="Illustrative engineering workflow">
            <div className={styles.exampleHeader}><span><FileCode2 size={15} aria-hidden="true" /> billing-service</span><span className={styles.exampleLabel}>Example project</span></div>
            <div className={styles.exampleTabs} role="tablist" aria-label="Explore the example" onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const next = event.key === "Home" ? 0 : event.key === "End" ? 2 : (active + (event.key === "ArrowRight" ? 1 : 2)) % 3;
              setActive(next);
              document.getElementById(`example-tab-${next}`)?.focus();
            }}>
              {example.map((tab, index) => <button key={tab.label} id={`example-tab-${index}`} role="tab" aria-selected={active === index} aria-controls="example-panel" tabIndex={active === index ? 0 : -1} onClick={() => setActive(index)}>{tab.label}</button>)}
            </div>
            <div id="example-panel" role="tabpanel" tabIndex={0} aria-labelledby={`example-tab-${active}`} className={styles.exampleBody}>
              <div className={styles.exampleIdentifier}><Icon size={16} aria-hidden="true" /><code>{item.id}</code></div>
              <h2>{item.title}</h2>
              <p>{item.description}</p>
              <dl>{item.rows.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
              <div className={styles.exampleFooter}><GitBranch size={14} aria-hidden="true" />{item.footer}</div>
            </div>
            <div className={styles.exampleCaption}><span>Illustrative workflow</span><span>Select a tab to explore</span></div>
          </div>
        </section>

        <div className={styles.lifecycle} aria-label="Engineering lifecycle">
          {["Requirement", "Architecture", "Plan", "Execution", "Evidence", "Pull request"].map((stage, index) => <span key={stage}>{stage}{index < 5 && <ChevronRight size={14} aria-hidden="true" />}</span>)}
        </div>

        <section id="workflow" className={styles.workflow} aria-labelledby="workflow-title">
          <div className={styles.sectionIntro}><h2 id="workflow-title">One project.<br />A connected workflow.</h2><p>Keep the brief, the decisions, and the work in the same place. Each stage gives the next one something concrete to build on.</p></div>
          <div className={styles.workflowRows}>{workflow.map(({ number, title, icon: StepIcon, text, workspaces }) => <article key={number} className={styles.workflowRow}>
            <span className={styles.stepNumber}>{number}</span><div><h3><StepIcon size={19} strokeWidth={1.6} aria-hidden="true" />{title}</h3><p>{text}</p><span className={styles.workspaceNames}>{workspaces}</span></div>
          </article>)}</div>
        </section>

        <section id="principles" className={styles.principles} aria-labelledby="principles-title">
          <div className={styles.principlesHeading}><LockKeyhole size={26} strokeWidth={1.5} aria-hidden="true" /><h2 id="principles-title">Move the work forward.<br />Keep the review in your hands.</h2><p>The workspace is built around explicit scope, human decisions, and inspectable evidence.</p></div>
          <ul>
            <li><Check size={17} aria-hidden="true" /><div><h3>Agree on the outcome</h3><p>Review acceptance criteria before implementation starts.</p></div></li>
            <li><Check size={17} aria-hidden="true" /><div><h3>Preserve the decision</h3><p>Versioned requirements keep the original agreement in view.</p></div></li>
            <li><Check size={17} aria-hidden="true" /><div><h3>Ask for the evidence</h3><p>Tests, evaluations, and changes belong in the review.</p></div></li>
          </ul>
        </section>

        <section className={styles.start} aria-labelledby="start-title"><div><h2 id="start-title">Start with the change you want to make.</h2><p>Create a project and give your engineering brief a home.</p></div><Button asChild size="lg"><Link href="/projects/new"><Plus size={17} aria-hidden="true" /> Create a project</Link></Button></section>
      </main>
      <footer className={styles.footer}><Link href="/" className={styles.footerBrand}><Code2 size={20} aria-hidden="true" /> Engineering workspace</Link><span>Requirements through evidenced delivery.</span><a href="https://github.com/tekeufranck681/agentic-engineering-workspace" aria-label="Engineering workspace on GitHub"><Github size={18} aria-hidden="true" /></a></footer>
    </div>
  );
}
