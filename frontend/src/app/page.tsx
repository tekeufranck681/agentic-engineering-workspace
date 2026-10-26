import Link from "next/link";
import { Button } from "@/components/ui/button";
export default function Home() {
  return (
    <main className="entry-page">
      <h1>Engineering workspace</h1>
      <p>Open a saved project to navigate its engineering workspaces.</p>
      <Button asChild>
        <Link href="/projects">Browse projects</Link>
      </Button>
      <p className="text-xs text-muted-foreground">
        Project creation and repository connection follow in the Overview task.
      </p>
    </main>
  );
}
