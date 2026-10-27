"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useRef, useState } from "react";
import { Code2, Menu, PanelRight, X, LayoutDashboard, FileText, Workflow, ListTodo, Activity, GitPullRequest, ArrowLeft, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { ProjectSwitcher } from "@/components/layout/project-switcher";
import { RightInspector } from "@/components/layout/right-inspector";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { useProject } from "@/lib/api/use-projects";
import { workspaces } from "@/lib/workspaces";
const workspaceIcons = [LayoutDashboard, FileText, Workflow, ListTodo, Activity, GitPullRequest];
export function AppShell({
  projectId,
  children,
  inspector,
}: {
  projectId: string;
  children: React.ReactNode;
  inspector?: React.ReactNode;
}) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const inspectorTrigger = useRef<HTMLButtonElement>(null);
  const closeInspector = useCallback(() => {
    setInspectorOpen(false);
    inspectorTrigger.current?.focus();
  }, []);
  const active = workspaces.find(
    (item) => pathname.split("/")[3] === item.slug,
  );
  const preview = projectId === "preview";
  const projectQuery = useProject(preview ? null : projectId);
  const project = projectQuery.data;
  const projectLabel = preview
    ? "Shell preview"
    : (project?.name ??
      (projectQuery.loading ? "Loading project…" : "Project unavailable"));
  const projectPath = `/projects/${encodeURIComponent(projectId)}`;
  return (
    <div
      className="app-shell"
      onKeyDown={(event) => {
        if (event.key === "Escape" && menuOpen) {
          setMenuOpen(false);
          menuButton.current?.focus();
        }
      }}
    >
      <a className="skip-link" href="#workspace-content">
        Skip to workspace
      </a>
      <aside className="sidebar" data-open={menuOpen} id="workspace-navigation">
        <Link className="brand" href="/">
          <Code2 size={18} aria-hidden="true" className="brand-symbol" />
          Engineering workspace
        </Link>
        <div className="project-context">
          <ProjectSwitcher
            projectId={projectId}
            projectLabel={projectLabel}
            workspace={active?.slug ?? "overview"}
            onNavigate={() => setMenuOpen(false)}
          />
        </div>
        <p className="workspace-nav-label">Workspace</p>
        <nav className="workspace-nav" aria-label="Project workspaces">
          {workspaces.map((item, index) => {
            const Icon = workspaceIcons[index];
            return (
            <Link
              key={item.slug}
              href={`/projects/${encodeURIComponent(projectId)}/${item.slug}`}
              aria-current={active?.slug === item.slug ? "page" : undefined}
              onClick={() => setMenuOpen(false)}
            >
              <Icon size={16} strokeWidth={1.7} aria-hidden="true" />
              {item.label}
            </Link>
          ); })}
        </nav>
        <Button asChild variant="outline" size="sm" className="sidebar-new-project"><Link href="/projects/new"><Plus size={14} aria-hidden="true" /> New project</Link></Button>
        <div className="sidebar-footer">
          <Link href="/projects" className="sidebar-back"><ArrowLeft size={14} aria-hidden="true" /> All projects</Link>
          <p className="preview-label">
            <span aria-hidden="true" />
            {preview
              ? "Preview mode"
              : project
                ? project.status === "active"
                  ? "Active project"
                  : "Archived project"
                : "Project not loaded"}
          </p>
          <p className="text-xs text-muted-foreground">
            {preview
              ? "Preview contains no saved project data."
              : "Repository and provider status appear in their workspaces."}
          </p>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-header">
          <Button
            ref={menuButton}
            variant="ghost"
            className="mobile-toggle"
            size="icon"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={menuOpen}
            aria-controls="workspace-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X size={18} /> : <Menu size={18} />}
          </Button>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link href="/projects">Projects</Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem className="project-breadcrumb">
                <BreadcrumbLink asChild>
                  <Link href={`${projectPath}/overview`} title={projectLabel}>
                    {projectLabel}
                  </Link>
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{active?.label ?? "Project"}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          <span className="header-note">
            {preview
              ? "Shell preview"
              : projectQuery.loading
                ? "Loading project…"
                : project
                  ? "Saved project"
                  : "Project unavailable"}
          </span>
          <Button
            ref={inspectorTrigger}
            variant="ghost"
            size="icon"
            aria-label="Open project details"
            aria-expanded={inspectorOpen}
            disabled={!project}
            onClick={() => setInspectorOpen((value) => !value)}
          >
            <PanelRight size={16} aria-hidden="true" />
          </Button>
        </header>
        <div className="workspace-panels">
          <main id="workspace-content" tabIndex={-1}>
            {!preview && projectQuery.loading ? (
              <LoadingState label="Loading project…" />
            ) : !preview && projectQuery.error ? (
              <ErrorState
                message={projectQuery.error.message}
                onRetry={projectQuery.retry}
              />
            ) : (
              children
            )}
          </main>
          {inspectorOpen && project && (
            <RightInspector title="Project details" onClose={closeInspector}>
              <dl className="project-details">
                <div>
                  <dt>Name</dt>
                  <dd>{project.name}</dd>
                </div>
                <div>
                  <dt>Project ID</dt>
                  <dd className="font-mono">{project.id}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>{project.status === "active" ? "Active" : "Archived"}</dd>
                </div>
                <div>
                  <dt>Description</dt>
                  <dd>{project.description ?? "No description provided."}</dd>
                </div>
                <div>
                  <dt>Created</dt>
                  <dd>
                    <time dateTime={project.created_at}>
                      {project.created_at}
                    </time>
                  </dd>
                </div>
                <div>
                  <dt>Updated</dt>
                  <dd>
                    <time dateTime={project.updated_at}>
                      {project.updated_at}
                    </time>
                  </dd>
                </div>
              </dl>
              {inspector}
            </RightInspector>
          )}
        </div>
      </div>
    </div>
  );
}
