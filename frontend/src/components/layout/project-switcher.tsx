"use client";
import { useState } from "react";
import Link from "next/link";
import { Check, ChevronsUpDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { useProjects } from "@/lib/api/use-projects";

export function ProjectSwitcher({
  projectId,
  projectLabel,
  workspace,
  onNavigate,
}: {
  projectId: string;
  projectLabel: string;
  workspace: string;
  onNavigate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const query = useProjects(0, open);
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          className="workspace-switcher"
          aria-label="Switch project"
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
        <DropdownMenuLabel>Projects</DropdownMenuLabel>
        {query.loading && (
          <div className="dropdown-message" role="status">
            Loading projects…
          </div>
        )}
        {query.error && (
          <>
            <p className="dropdown-message" role="alert">
              Projects could not be loaded.
            </p>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                query.retry();
              }}
            >
              Try again
            </DropdownMenuItem>
          </>
        )}
        {query.data?.length === 0 && (
          <p className="dropdown-message">No saved projects yet.</p>
        )}
        {query.data?.map((project) => (
          <DropdownMenuItem key={project.id} asChild>
            <Link
              href={`/projects/${project.id}/${workspace}`}
              onClick={onNavigate}
            >
              <span className="truncate">{project.name}</span>
              {project.id === projectId && (
                <Check size={14} className="shrink-0" aria-hidden="true" />
              )}
            </Link>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/projects" onClick={onNavigate}>
            Browse projects
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href={`/projects/preview/${workspace}`} onClick={onNavigate}>
            Shell preview
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
