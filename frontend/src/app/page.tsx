import Link from "next/link";
import { Button } from "@/components/ui/button";
export default function Home() {
  return (
    <main className="entry-page">
      <h1>Engineering workspace</h1>
      <p>
        The shared frontend shell is ready for screen integration. Project
        creation and repository connection are not connected yet.
      </p>
      <Button asChild>
        <Link href="/projects/preview/overview">Open shell preview</Link>
      </Button>
      <p className="text-xs text-muted-foreground">
        Preview routes contain no persisted project or simulated agent activity.
      </p>
    </main>
  );
}
