"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useRef, useState } from "react";
import { Check, ChevronsUpDown, Code2, Menu, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Breadcrumb,
  BreadcrumbList,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
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
  const projectLabel = projectId === "preview" ? "Shell preview" : projectId;
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
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                className="workspace-switcher"
                aria-label="Open workspace navigation"
              >
                <span className="workspace-initial" aria-hidden="true">
                  {projectLabel.slice(0, 1).toUpperCase()}
                </span>
                <span className="project-id" title={projectLabel}>
                  {projectLabel}
                </span>
                <ChevronsUpDown
                  size={14}
                  className="shrink-0 text-muted-foreground"
                  aria-hidden="true"
                />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start">
              <DropdownMenuLabel>Workspace pages</DropdownMenuLabel>
              {workspaces.map((item) => (
                <DropdownMenuItem asChild key={item.slug}>
                  <Link
                    href={`${projectPath}/${item.slug}`}
                    onClick={() => setMenuOpen(false)}
                  >
                    <span>{item.label}</span>
                    {active?.slug === item.slug && (
                      <Check size={14} aria-hidden="true" />
                    )}
                  </Link>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem asChild>
                <Link href="/">Workspace entry</Link>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
        <nav className="workspace-nav" aria-label="Project workspaces">
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
          <p className="preview-label">
            <span aria-hidden="true" />
            Preview mode
          </p>
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
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink asChild>
                  <Link href="/">Workspace</Link>
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
