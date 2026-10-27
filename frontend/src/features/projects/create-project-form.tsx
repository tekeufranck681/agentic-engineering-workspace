"use client";
import { Plus } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { parseProjectCreate } from "@/lib/api/project-contract";
import { useProjectsStore } from "@/stores/projectsStore";
export function CreateProjectForm() {
  const router = useRouter();
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const creating = useProjectsStore((state) => state.creating);
  const error = useProjectsStore((state) => state.createError);
  const create = useProjectsStore((state) => state.createProject);
  const clearError = useProjectsStore((state) => state.clearCreateError);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (creating || error?.uncertain) return;
    let input;
    try {
      input = parseProjectCreate({ name, description });
      setValidation(null);
    } catch (error) {
      setValidation(
        error instanceof Error ? error.message : "Check the project details.",
      );
      return;
    }
    try {
      const project = await create(input);
      if (mounted.current) router.push(`/projects/${project.id}/overview`);
    } catch {
      /* The store exposes the confirmed request error. */
    }
  }
  return (
    <main className="project-form-page">
      <Link className="back-link" href="/projects">
        Back to projects
      </Link>
      <h1>Create project</h1>
      <p className="page-description">
        Name the engineering workspace. You can link its GitHub repository next.
      </p>
      <form onSubmit={submit} className="project-form" aria-busy={creating}>
        <div className="form-field">
          <label htmlFor="project-name">Project name</label>
          <Input
            id="project-name"
            autoComplete="off"
            maxLength={200}
            required
            value={name}
            disabled={creating}
            onChange={(event) => {
              setName(event.target.value);
              setValidation(null);
              if (!error?.uncertain) clearError();
            }}
          />
        </div>
        <div className="form-field">
          <label htmlFor="project-description">
            Description{" "}
            <span className="text-muted-foreground">(optional)</span>
          </label>
          <textarea
            id="project-description"
            className="form-input"
            rows={4}
            maxLength={5000}
            value={description}
            disabled={creating}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        {(validation || error) && (
          <div className="form-error" role="alert">
            <p>{validation ?? error?.message}</p>
            {error?.uncertain && (
              <Link href="/projects">Check saved projects before retrying</Link>
            )}
          </div>
        )}
        <div className="state-actions">
          <Button type="submit" disabled={creating || error?.uncertain}>
            <Plus size={15} aria-hidden="true" />
            {creating ? "Creating project…" : "Create project"}
          </Button>
          <Button
            type="button"
            variant="ghost"
            disabled={creating}
            onClick={() => router.push("/projects")}
          >
            Cancel
          </Button>
        </div>
      </form>
    </main>
  );
}
