import Link from "next/link";
export default function NotFound() {
  return (
    <div className="entry-page">
      <h1>Workspace not found</h1>
      <p>Choose one of the six supported workspaces.</p>
      <Link href="/">Return to workspace entry</Link>
    </div>
  );
}
