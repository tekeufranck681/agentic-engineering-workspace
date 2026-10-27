"use client";
import { useCallback, useEffect, useState } from "react";
import { parseProject, parseProjects } from "./project-contract";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}
function useProjectQuery<T>(path: string | null, parse: (value: unknown) => T) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{
    key: string;
    data: T | null;
    error: ApiError | null;
  }>({ key: "", data: null, error: null });
  const key = `${path}:${attempt}`;
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(path!, {
          signal: controller.signal,
          cache: "no-store",
        });
        const body: unknown = await response.json();
        if (!response.ok) {
          const message =
            typeof body === "object" &&
            body !== null &&
            "message" in body &&
            typeof body.message === "string"
              ? body.message
              : "Could not load project data. Try again.";
          throw new ApiError(response.status, message);
        }
        const data = parse(body);
        if (!controller.signal.aborted) setResult({ key, data, error: null });
      } catch (error) {
        if (!controller.signal.aborted)
          setResult({
            key,
            data: null,
            error:
              error instanceof ApiError
                ? error
                : new ApiError(
                    0,
                    "Could not load project data. Check your connection and try again.",
                  ),
          });
      }
    }
    void load();
    return () => controller.abort();
  }, [path, key, parse]);
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  const current = result.key === key;
  return {
    data: current ? result.data : null,
    error: current ? result.error : null,
    loading: path !== null && !current,
    retry,
  };
}
export function useProjects(offset = 0, enabled = true) {
  return useProjectQuery(
    enabled ? `/api/projects?offset=${offset}` : null,
    parseProjects,
  );
}
export function useProject(id: string | null) {
  return useProjectQuery(
    id ? `/api/projects/${encodeURIComponent(id)}` : null,
    parseProject,
  );
}
