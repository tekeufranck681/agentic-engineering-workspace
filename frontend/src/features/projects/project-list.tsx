"use client";
import { useState } from "react";
import Link from "next/link";
import { useProjectsStore } from "@/stores/projectsStore";
import { useProjects } from "@/lib/api/use-projects";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/shared/loading-state";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorState } from "@/components/shared/error-state";
import { StatusBadge } from "@/components/shared/status-badge";

export function ProjectList() {
  const [offset, setOffset] = useState(0);
  const query = useProjects(offset);
  const clearCreateError = useProjectsStore((state) => state.clearCreateError);
  return (
    <main className="projects-page">
      <div className="page-heading">
        <h1>Projects</h1>
        <div className="projects-actions">
          <Button
            variant="outline"
            onClick={query.retry}
            disabled={query.loading}
          >
            Refresh
          </Button>
          <Button asChild>
            <Link href="/projects/new" onClick={clearCreateError}>
              Create project
            </Link>
          </Button>
        </div>
      </div>
      <p className="page-description">
        Open a project to continue its engineering workflow.
      </p>
      {query.loading ? (
        <LoadingState label="Loading projects…" />
      ) : query.error ? (
        <ErrorState message={query.error.message} onRetry={query.retry} />
      ) : query.data && query.data.length ? (
        <ul className="project-list">
          {query.data.map((project) => (
            <li key={project.id}>
              <Link href={`/projects/${project.id}/overview`}>
                <div>
                  <span className="project-list-name">{project.name}</span>
                  {project.description && <p>{project.description}</p>}
                </div>
                <StatusBadge>
                  {project.status === "active" ? "Active" : "Archived"}
                </StatusBadge>
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title={offset ? "No more projects" : "No projects yet"}
          action={
            <Button variant="outline" onClick={query.retry}>
              Refresh projects
            </Button>
          }
        >
          <p>
            {offset
              ? "Return to the previous page to choose a project."
              : "No saved projects were returned. Create a project to start organizing its requirements and repository."}
          </p>
        </EmptyState>
      )}
      {(offset > 0 || query.data?.length === 100) && (
        <div className="state-actions">
          <Button
            variant="outline"
            disabled={offset === 0 || query.loading}
            onClick={() => setOffset((value) => Math.max(0, value - 100))}
          >
            Previous projects
          </Button>
          <Button
            variant="outline"
            disabled={query.loading || query.data?.length !== 100}
            onClick={() => setOffset((value) => value + 100)}
          >
            More projects
          </Button>
        </div>
      )}
      <div className="projects-footer">
        <Link href="/projects/preview/overview">Open shell preview</Link>
        <span>Preview contains no saved project data.</span>
      </div>
    </main>
  );
}
