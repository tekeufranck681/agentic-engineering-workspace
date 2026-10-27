"use client";
import { useState } from "react";
import Link from "next/link";
import { useProject, useRepositoryBinding } from "@/lib/api/use-projects";
import { useProjectsStore } from "@/stores/projectsStore";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/shared/status-badge";
import { LoadingState } from "@/components/shared/loading-state";
import { ErrorState } from "@/components/shared/error-state";
import { EmptyState } from "@/components/shared/empty-state";
import { RepositoryForm } from "./repository-form";
const summaries = [
  {
    title: "Current requirement",
    description:
      "The current requirement is not reported for this project yet.",
    href: "requirements",
    action: "Open requirements",
  },
  {
    title: "Last agent run",
    description: "Run history is not reported for this project yet.",
    href: "runs",
    action: "Open Agent Runs",
  },
  {
    title: "Pending approvals",
    description:
      "Approval status is unavailable. Do not assume that no review is needed.",
    href: null,
    action: null,
  },
  {
    title: "Recent evidence",
    description: "Evidence summaries are unavailable for this project.",
    href: "delivery",
    action: "Open delivery",
  },
];
export function OverviewWorkspace({ projectId }: { projectId: string }) {
  const { data: project } = useProject(projectId);
  const query = useRepositoryBinding(projectId);
  const [editing, setEditing] = useState<string | null>(null);
  const [notice, setNotice] = useState(false);
  const clearBindingError = useProjectsStore(
    (state) => state.clearBindingError,
  );
  if (!project) return null;
  const binding = query.data;
  const showForm =
    !query.loading && !query.error && (!binding || editing === binding.id);
  return (
    <div className="workspace-page overview-page">
      <div className="page-heading">
        <h1>Overview</h1>
        <StatusBadge>
          {project.status === "active" ? "Active project" : "Archived project"}
        </StatusBadge>
      </div>
      <p className="page-description">
        {project.description ??
          "Project context, repository and the next engineering action."}
      </p>
      <section className="overview-next" aria-labelledby="next-action-title">
        <div>
          <h2 id="next-action-title">Next action</h2>
          <p>
            {query.loading
              ? "Loading repository context…"
              : query.error
                ? "Restore the repository connection details to continue."
                : !binding
                  ? "Link the approved GitHub repository to this project."
                  : !binding.base_sha
                    ? "Resolve the base commit before starting an implementation run."
                    : "Review requirements and repository access before planning an implementation run."}
          </p>
        </div>
        <Button asChild variant="outline">
          <a href="#repository-connection">Review repository</a>
        </Button>
      </section>
      <section
        id="repository-connection"
        className="overview-section"
        aria-labelledby="repository-heading"
      >
        <div className="section-heading">
          <h2 id="repository-heading">GitHub repository</h2>
          {binding && <StatusBadge>Link saved</StatusBadge>}
        </div>
        {query.loading ? (
          <LoadingState label="Loading repository link…" />
        ) : query.error ? (
          <ErrorState message={query.error.message} onRetry={query.retry} />
        ) : binding ? (
          <>
            <dl className="repository-summary">
              <div>
                <dt>Repository</dt>
                <dd>
                  <a
                    href={`https://github.com/${binding.owner}/${binding.name}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {binding.full_name}
                  </a>
                </dd>
              </div>
              <div>
                <dt>Base branch</dt>
                <dd className="font-mono">{binding.default_branch}</dd>
              </div>
              <div>
                <dt>Base commit</dt>
                <dd className="font-mono">
                  {binding.base_sha ?? "Not resolved"}
                </dd>
              </div>
              <div>
                <dt>Access verification</dt>
                <dd>Not reported</dd>
              </div>
            </dl>
            <p className="text-xs text-muted-foreground">
              A saved link does not establish repository access or permission to
              run code.
            </p>
            {!showForm && (
              <Button
                variant="outline"
                className="mt-4"
                onClick={() => {
                  clearBindingError(projectId);
                  setEditing(binding.id);
                  setNotice(false);
                }}
              >
                Link a different repository
              </Button>
            )}
          </>
        ) : (
          <EmptyState title="No repository linked">
            <p>
              Save the repository details below to associate this project with
              its demo target.
            </p>
          </EmptyState>
        )}
        {notice && (
          <p className="save-notice" role="status">
            Repository association saved.
          </p>
        )}
        {showForm && (
          <RepositoryForm
            key={binding?.id ?? "new"}
            projectId={projectId}
            existing={binding}
            onSaved={() => {
              setEditing(null);
              setNotice(true);
            }}
            onCancel={() => setEditing(null)}
          />
        )}
      </section>
      <section className="overview-section" aria-labelledby="activity-heading">
        <h2 id="activity-heading">Engineering activity</h2>
        <div className="overview-summaries">
          {summaries.map((summary) => (
            <div className="overview-summary" key={summary.title}>
              <div>
                <h3>{summary.title}</h3>
                <p>{summary.description}</p>
                {summary.href && (
                  <Link href={`/projects/${projectId}/${summary.href}`}>
                    {summary.action}
                  </Link>
                )}
              </div>
              <StatusBadge>Unavailable</StatusBadge>
            </div>
          ))}
        </div>
      </section>
      <section className="overview-section provider-availability">
        <h2>Provider readiness</h2>
        <StatusBadge>Unavailable</StatusBadge>
        <p>
          Provider readiness is not reported for this project yet. Confirm
          availability before starting a run.
        </p>
      </section>
    </div>
  );
}
