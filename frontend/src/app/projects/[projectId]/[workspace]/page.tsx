import { notFound } from "next/navigation";
import { workspaces } from "@/lib/workspaces";
import { StatusBadge } from "@/components/shared/status-badge";
export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ workspace: string }>;
}) {
  const { workspace } = await params;
  const section = workspaces.find((item) => item.slug === workspace);
  if (!section) notFound();
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
            <dd>No project data loaded</dd>
          </div>
        </dl>
      </section>
    </div>
  );
}
