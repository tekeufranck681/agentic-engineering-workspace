"use client";
import Link from "next/link";
import { Button } from "@/components/ui/button";
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <section className="query-state" role="alert">
      <h2>Project data unavailable</h2>
      <p className="state-description">{message}</p>
      <div className="state-actions">
        {onRetry && (
          <Button variant="outline" onClick={onRetry}>
            Try again
          </Button>
        )}
        <Button variant="ghost" asChild>
          <Link href="/projects">Choose a project</Link>
        </Button>
      </div>
    </section>
  );
}
