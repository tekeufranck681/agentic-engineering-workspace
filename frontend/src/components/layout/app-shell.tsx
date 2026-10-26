"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { workspaces } from "@/lib/workspaces";
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
  const active = workspaces.find((item) => pathname.endsWith("/" + item.slug));
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
          Engineering workspace
        </Link>
        <div className="project-context">
          <span className="text-xs text-muted-foreground">Project context</span>
          <span className="project-id" title={projectId}>
            {projectId === "preview" ? "Shell preview" : projectId}
          </span>
        </div>
        <nav aria-label="Project workspaces">
          {workspaces.map((item) => (
            <Link
              key={item.slug}
              href={`/projects/${encodeURIComponent(projectId)}/${item.slug}`}
              aria-current={active?.slug === item.slug ? "page" : undefined}
              onClick={() => setMenuOpen(false)}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="sidebar-footer">
          <p>Development shell</p>
          <p className="text-xs text-muted-foreground">
            Repository and provider status will appear after API integration.
          </p>
        </div>
      </aside>
      <div className="workspace-body">
        <header className="workspace-header">
          <Button
            ref={menuButton}
            variant="ghost"
            className="mobile-toggle"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={menuOpen}
            aria-controls="workspace-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X size={18} /> : <Menu size={18} />}
          </Button>
          <span className="text-muted-foreground">Workspace</span>
          <span aria-hidden="true">/</span>
          <span>{active?.label ?? "Project"}</span>
          <span className="header-note">Backend not connected</span>
        </header>
        <div className="workspace-panels">
          <main id="workspace-content" tabIndex={-1}>
            {children}
          </main>
          {inspector && (
            <aside className="inspector" aria-label="Artifact details">
              {inspector}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
