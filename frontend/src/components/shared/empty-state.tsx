export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <section className="query-state">
      <h2>{title}</h2>
      <div className="state-description">{children}</div>
      {action && <div className="state-actions">{action}</div>}
    </section>
  );
}
