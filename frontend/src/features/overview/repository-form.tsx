"use client";
import { useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  bindingFromUrl,
  type RepositoryBinding,
} from "@/lib/api/project-contract";
import { useProjectsStore } from "@/stores/projectsStore";
export function RepositoryForm({
  projectId,
  existing,
  onSaved,
  onCancel,
}: {
  projectId: string;
  existing: RepositoryBinding | null;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [sha, setSha] = useState("");
  const [replace, setReplace] = useState(false);
  const [validation, setValidation] = useState<string | null>(null);
  const write = useProjectsStore((state) => state.bindingWrites[projectId]);
  const bind = useProjectsStore((state) => state.bindRepository);
  const pending = write?.pending ?? false;
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (pending || write?.error?.uncertain) return;
    let input;
    try {
      input = bindingFromUrl(url, branch, sha);
      if (
        existing &&
        `${input.owner}/${input.name}`.toLowerCase() ===
          existing.full_name.toLowerCase()
      )
        throw new Error(
          "This repository is already linked. Updating its branch or commit metadata is not supported yet.",
        );
      if (existing && !replace)
        throw new Error("Confirm replacement of the current repository link.");
      setValidation(null);
    } catch (error) {
      setValidation(
        error instanceof Error
          ? error.message
          : "Check the repository details.",
      );
      return;
    }
    try {
      await bind(projectId, input);
      onSaved();
    } catch {
      /* Mutation outcome is rendered from the store. */
    }
  }
  return (
    <form
      className="project-form repository-form"
      onSubmit={submit}
      aria-busy={pending}
    >
      <p className="state-description">
        Use the approved demo target repository. This saves its association with
        the project; GitHub access is checked separately.
      </p>
      <div className="form-field">
        <label htmlFor="repository-url">GitHub repository URL</label>
        <Input
          id="repository-url"
          type="url"
          placeholder="https://github.com/owner/repository"
          required
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          disabled={pending}
        />
      </div>
      <div className="repository-fields">
        <div className="form-field">
          <label htmlFor="repository-branch">Base branch</label>
          <Input
            id="repository-branch"
            placeholder="main"
            maxLength={200}
            required
            value={branch}
            onChange={(event) => setBranch(event.target.value)}
            disabled={pending}
          />
        </div>
        <div className="form-field">
          <label htmlFor="repository-sha">
            Base commit SHA{" "}
            <span className="text-muted-foreground">(if known)</span>
          </label>
          <Input
            id="repository-sha"
            className="font-mono"
            minLength={7}
            maxLength={40}
            value={sha}
            onChange={(event) => setSha(event.target.value)}
            disabled={pending}
          />
        </div>
      </div>
      {!sha && (
        <p className="text-xs text-muted-foreground">
          A base commit is required before autonomous implementation can begin.
        </p>
      )}
      {existing && (
        <label className="form-checkbox">
          <input
            type="checkbox"
            required
            checked={replace}
            onChange={(event) => setReplace(event.target.checked)}
            disabled={pending}
          />
          Replace the current link to {existing.full_name}. Its history is
          retained.
        </label>
      )}
      {(validation || write?.error) && (
        <div className="form-error" role="alert">
          <p>{validation ?? write?.error?.message}</p>
          {write?.error?.uncertain && (
            <a href={`/projects/${projectId}/overview`}>
              Reload saved repository details before retrying
            </a>
          )}
        </div>
      )}
      <div className="state-actions">
        <Button type="submit" disabled={pending || write?.error?.uncertain}>
          {pending ? "Saving repository link…" : "Save repository link"}
        </Button>
        {existing && (
          <Button
            type="button"
            variant="ghost"
            disabled={pending}
            onClick={onCancel}
          >
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
