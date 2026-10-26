"use client";
import { create } from "zustand";
import { projectsService } from "@/services/projectsService";
import { ApiError } from "@/lib/api/client";
import type {
  Project,
  ProjectCreate,
  RepositoryBinding,
  RepositoryBindingCreate,
} from "@/lib/api/project-contract";
export interface QueryState<T> {
  data: T | null;
  loading: boolean;
  fetched: boolean;
  error: ApiError | null;
}
export const emptyProject: QueryState<Project> = {
  data: null,
  loading: false,
  fetched: false,
  error: null,
};
export const emptyPage: QueryState<Project[]> = { ...emptyProject, data: null };
export const emptyBinding: QueryState<RepositoryBinding | null> = {
  ...emptyProject,
  data: null,
};
const inFlight = new Map<string, Promise<void>>();
let createRequest: Promise<Project> | null = null;
const bindRequests = new Map<string, Promise<RepositoryBinding>>();
const errorOf = (error: unknown) =>
  error instanceof ApiError
    ? error
    : new ApiError(0, "The request could not be completed.");
interface ProjectsState {
  projects: Record<string, QueryState<Project>>;
  pages: Record<number, QueryState<Project[]>>;
  bindings: Record<string, QueryState<RepositoryBinding | null>>;
  creating: boolean;
  createError: ApiError | null;
  bindingWrites: Record<string, { pending: boolean; error: ApiError | null }>;
  fetchProject: (id: string, force?: boolean) => Promise<void>;
  fetchProjects: (offset: number, force?: boolean) => Promise<void>;
  fetchBinding: (id: string, force?: boolean) => Promise<void>;
  createProject: (input: ProjectCreate) => Promise<Project>;
  bindRepository: (
    id: string,
    input: RepositoryBindingCreate,
  ) => Promise<RepositoryBinding>;
  clearCreateError: () => void;
  clearBindingError: (id: string) => void;
}
async function read<T>(
  key: string,
  request: () => Promise<T>,
  commit: (result: QueryState<T>) => void,
  previous: QueryState<T>,
) {
  if (inFlight.has(key)) return inFlight.get(key);
  const promise = (async () => {
    commit({ ...previous, loading: true, error: null });
    try {
      const data = await request();
      commit({ data, loading: false, fetched: true, error: null });
    } catch (error) {
      commit({
        ...previous,
        loading: false,
        fetched: true,
        error: errorOf(error),
      });
    }
  })();
  inFlight.set(key, promise);
  try {
    await promise;
  } finally {
    inFlight.delete(key);
  }
}
export const useProjectsStore = create<ProjectsState>((set, get) => ({
  projects: {},
  pages: {},
  bindings: {},
  creating: false,
  createError: null,
  bindingWrites: {},
  fetchProject: (id, force = false) => {
    const previous = get().projects[id] ?? emptyProject;
    if (previous.fetched && !force) return Promise.resolve();
    return read(
      `project:${id}`,
      () => projectsService.get(id),
      (result) =>
        set((state) => ({ projects: { ...state.projects, [id]: result } })),
      previous,
    );
  },
  fetchProjects: (offset, force = false) => {
    const previous = get().pages[offset] ?? emptyPage;
    if (previous.fetched && !force) return Promise.resolve();
    return read(
      `page:${offset}`,
      () => projectsService.list(offset),
      (result) =>
        set((state) => ({ pages: { ...state.pages, [offset]: result } })),
      previous,
    );
  },
  fetchBinding: (id, force = false) => {
    const previous = get().bindings[id] ?? emptyBinding;
    if (previous.fetched && !force) return Promise.resolve();
    return read(
      `binding:${id}`,
      () => projectsService.getBinding(id),
      (result) =>
        set((state) => ({ bindings: { ...state.bindings, [id]: result } })),
      previous,
    );
  },
  createProject: (input) => {
    if (createRequest) return createRequest;
    createRequest = (async () => {
      await Promise.resolve();
      set({ creating: true, createError: null });
      try {
        const project = await projectsService.create(input);
        set((state) => ({
          projects: {
            ...state.projects,
            [project.id]: {
              data: project,
              loading: false,
              fetched: true,
              error: null,
            },
          },
          pages: {},
        }));
        return project;
      } catch (error) {
        const normalized = errorOf(error);
        set({ createError: normalized });
        throw normalized;
      } finally {
        set({ creating: false });
        createRequest = null;
      }
    })();
    return createRequest;
  },
  bindRepository: (id, input) => {
    const existing = bindRequests.get(id);
    if (existing) return existing;
    const request = (async () => {
      await Promise.resolve();
      set((state) => ({
        bindingWrites: {
          ...state.bindingWrites,
          [id]: { pending: true, error: null },
        },
      }));
      try {
        const binding = await projectsService.bind(id, input);
        set((state) => ({
          bindings: {
            ...state.bindings,
            [id]: { data: binding, loading: false, fetched: true, error: null },
          },
        }));
        return binding;
      } catch (error) {
        const normalized = errorOf(error);
        set((state) => ({
          bindingWrites: {
            ...state.bindingWrites,
            [id]: { pending: true, error: normalized },
          },
        }));
        throw normalized;
      } finally {
        set((state) => ({
          bindingWrites: {
            ...state.bindingWrites,
            [id]: {
              pending: false,
              error: state.bindingWrites[id]?.error ?? null,
            },
          },
        }));
        bindRequests.delete(id);
      }
    })();
    bindRequests.set(id, request);
    return request;
  },
  clearCreateError: () => set({ createError: null }),
  clearBindingError: (id) =>
    set((state) => ({
      bindingWrites: {
        ...state.bindingWrites,
        [id]: { pending: false, error: null },
      },
    })),
}));
