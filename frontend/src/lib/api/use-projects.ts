"use client";
import { useCallback, useEffect } from "react";
import {
  useProjectsStore,
  emptyProject,
  emptyPage,
  emptyBinding,
} from "@/stores/projectsStore";
export { ApiError } from "./client";
export function useProjects(offset = 0, enabled = true) {
  const state = useProjectsStore((store) => store.pages[offset] ?? emptyPage);
  const load = useProjectsStore((store) => store.fetchProjects);
  useEffect(() => {
    if (enabled) void load(offset);
  }, [enabled, offset, load, state.fetched]);
  const retry = useCallback(() => {
    void load(offset, true);
  }, [offset, load]);
  return {
    data: enabled ? state.data : null,
    error: enabled ? state.error : null,
    loading: enabled && (!state.fetched || state.loading),
    retry,
  };
}
export function useProject(id: string | null) {
  const state = useProjectsStore((store) =>
    id ? (store.projects[id] ?? emptyProject) : emptyProject,
  );
  const load = useProjectsStore((store) => store.fetchProject);
  useEffect(() => {
    if (id) void load(id);
  }, [id, load, state.fetched]);
  const retry = useCallback(() => {
    if (id) void load(id, true);
  }, [id, load]);
  return {
    data: state.data,
    error: state.error,
    loading: !!id && (!state.fetched || state.loading),
    retry,
  };
}
export function useRepositoryBinding(id: string | null) {
  const state = useProjectsStore((store) =>
    id ? (store.bindings[id] ?? emptyBinding) : emptyBinding,
  );
  const load = useProjectsStore((store) => store.fetchBinding);
  useEffect(() => {
    if (id) void load(id);
  }, [id, load, state.fetched]);
  const retry = useCallback(() => {
    if (id) void load(id, true);
  }, [id, load]);
  return {
    data: state.data,
    error: state.error,
    loading: !!id && (!state.fetched || state.loading),
    retry,
  };
}
