export function LoadingState({
  label = "Loading workspace…",
}: {
  label?: string;
}) {
  return (
    <div className="query-state" role="status" aria-live="polite">
      <p>{label}</p>
      <div className="loading-line" aria-hidden="true" />
    </div>
  );
}
