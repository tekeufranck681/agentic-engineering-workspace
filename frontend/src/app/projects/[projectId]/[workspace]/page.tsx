import Link from "next/link";
import { RequirementsWorkspace } from "@/features/requirements/requirements-workspace";
import { OverviewWorkspace } from "@/features/overview/overview-workspace";
import { ArchitectureWorkspace } from "@/features/architecture/architecture-workspace";
import { PlanningWorkspace } from "@/features/planning/planning-workspace";
import { Button } from "@/components/ui/button";
import { notFound } from "next/navigation";
import { workspaces } from "@/lib/workspaces";
import { StatusBadge } from "@/components/shared/status-badge";
export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ workspace: string; projectId: string }>;
}) {
  const { workspace, projectId } = await params;
  const section = workspaces.find((item) => item.slug === workspace);
  if (!section) notFound();
  if (workspace === "requirements") return <RequirementsWorkspace key={projectId} projectId={projectId} />;
  if (workspace === "architecture") return <ArchitectureWorkspace key={projectId} projectId={projectId} />;
  if (workspace === "planning") return <PlanningWorkspace key={projectId} projectId={projectId} />;
  if (workspace === "overview" && projectId !== "preview")
    return <OverviewWorkspace projectId={projectId} />;
  if (workspace === "overview")
    return (
      <div className="workspace-page">
        <h1>Overview</h1>
        <p className="page-description">
          This is the shell preview. Open or create a saved project to inspect
          its repository context.
        </p>
        <div className="state-actions">
          <Button asChild>
            <Link href="/projects">Browse projects</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/projects/new">Create project</Link>
          </Button>
        </div>
      </div>
    );
  return (
    <div className="workspace-page">
      <div className="page-heading">
        <h1>{section.label}</h1>
        <StatusBadge>Placeholder</StatusBadge>
      </div>
      <p className="page-description">{section.description}</p>
      <section className="empty-state" aria-labelledby="integration-title">
        <h2 id="integration-title">Workspace integration pending</h2>
        <p>
          This route verifies the shared layout and navigation. Project records
          and engineering actions will appear when this screen is connected to
          its backend contract.
        </p>
        <dl>
          <div>
            <dt>Implementation task</dt>
            <dd className="font-mono">{section.task}</dd>
          </div>
          <div>
            <dt>Displayed data</dt>
            <dd>No workspace artifacts loaded</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
