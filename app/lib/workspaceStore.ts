// Workspace state shared by the pages (P1 spec 4).
//
// One external store holds the last workspace answer and the service state;
// pages subscribe to the slice they use with useWorkspaceSelector (React
// useSyncExternalStore), so a poll that changes only the Run list does not
// re-render a page that reads only the data packs.  New answers are merged by
// structural sharing (poll.ts): unchanged parts keep their object identity.
//
// Selectors must return a part of the snapshot or a primitive.  A selector
// that builds a new array or object should pass an `isEqual` (for example
// shallowEqualArray) or derive the value with useMemo in the page instead.
import { createContext, createElement, useContext, useMemo, useSyncExternalStore, type ReactNode } from "react";
import type { Workspace } from "../features/shared/workspaceTypes";
import { replaceEqualDeep } from "./poll.ts";

export type HealthPayload = {
  status: string;
  version?: string;
  frontend_contract_version?: string;
  degraded_reasons?: { code: string; count: number }[];
};

export type WorkspaceSnapshot = {
  workspace: Workspace;
  /** True once a workspace answer has arrived. */
  loaded: boolean;
  /** True while the last read succeeded. */
  online: boolean;
  /** Consecutive failed workspace reads. */
  failures: number;
  /** The last /api/health answer (null when unknown or failed). */
  health: HealthPayload | null;
  /** The page did not come through the VALUE launcher (whole-page notice). */
  launcherRequired: boolean;
};

export type WorkspaceStore = {
  getSnapshot: () => WorkspaceSnapshot;
  subscribe: (listener: () => void) => () => void;
  /** Merge a new workspace answer (structural sharing) and mark the service online. */
  receiveWorkspace: (workspace: Workspace) => Workspace;
  /** Change other fields of the snapshot. */
  update: (patch: Partial<Omit<WorkspaceSnapshot, "workspace">>) => void;
};

export function createWorkspaceStore(initialWorkspace: Workspace): WorkspaceStore {
  let snapshot: WorkspaceSnapshot = {
    workspace: initialWorkspace, loaded: false, online: false, failures: 0, health: null, launcherRequired: false,
  };
  const listeners = new Set<() => void>();
  const emit = () => { for (const listener of [...listeners]) listener(); };
  const set = (next: WorkspaceSnapshot) => {
    const changed = (Object.keys(next) as (keyof WorkspaceSnapshot)[]).some((key) => !Object.is(next[key], snapshot[key]));
    if (!changed) return;
    snapshot = next;
    emit();
  };
  return {
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => { listeners.delete(listener); };
    },
    receiveWorkspace(workspace) {
      const shared = replaceEqualDeep(snapshot.workspace, workspace);
      set({ ...snapshot, workspace: shared, loaded: true, online: true, failures: 0 });
      return shared;
    },
    update(patch) {
      const health = "health" in patch ? replaceEqualDeep(snapshot.health, patch.health ?? null) : snapshot.health;
      set({ ...snapshot, ...patch, health });
    },
  };
}

const WorkspaceStoreContext = createContext<WorkspaceStore | null>(null);

export function WorkspaceStoreProvider({ store, children }: { store: WorkspaceStore; children?: ReactNode }) {
  return createElement(WorkspaceStoreContext.Provider, { value: store }, children);
}

/** The store of the nearest WorkspaceStoreProvider. */
export function useWorkspaceStore(): WorkspaceStore {
  const store = useContext(WorkspaceStoreContext);
  if (!store) throw new Error("useWorkspaceStore needs a WorkspaceStoreProvider");
  return store;
}

/** A memoised selector over the store: the same selection object while the snapshot (or an equal selection) is unchanged. */
export function selectFrom<S>(store: WorkspaceStore, selector: (snapshot: WorkspaceSnapshot) => S, isEqual: (a: S, b: S) => boolean = Object.is): () => S {
  let hasSelection = false;
  let lastSnapshot: WorkspaceSnapshot | null = null;
  let lastSelection: S;
  return () => {
    const current = store.getSnapshot();
    if (hasSelection && current === lastSnapshot) return lastSelection;
    const next = selector(current);
    lastSnapshot = current;
    if (hasSelection && isEqual(lastSelection, next)) return lastSelection;
    hasSelection = true;
    lastSelection = next;
    return next;
  };
}

/**
 * Subscribe to one slice of the workspace store.  The component re-renders
 * only when that slice changes.  `store` defaults to the provider's store.
 */
export function useWorkspaceSelector<S>(selector: (snapshot: WorkspaceSnapshot) => S, options: { isEqual?: (a: S, b: S) => boolean; store?: WorkspaceStore } = {}): S {
  const contextStore = useContext(WorkspaceStoreContext);
  const store = options.store ?? contextStore;
  if (!store) throw new Error("useWorkspaceSelector needs a WorkspaceStoreProvider or a store");
  const { isEqual } = options;
  const getSelection = useMemo(() => selectFrom(store, selector, isEqual), [store, selector, isEqual]);
  return useSyncExternalStore(store.subscribe, getSelection, getSelection);
}

/** Element-wise identity of two arrays (for selectors that filter). */
export function shallowEqualArray<T>(a: readonly T[], b: readonly T[]): boolean {
  return a.length === b.length && a.every((item, index) => Object.is(item, b[index]));
}

// Common slices: module-level functions, so their identity is stable.
export const selectWorkspace = (snapshot: WorkspaceSnapshot) => snapshot.workspace;
export const selectRuns = (snapshot: WorkspaceSnapshot) => snapshot.workspace.runs;
export const selectProjects = (snapshot: WorkspaceSnapshot) => snapshot.workspace.projects;
export const selectDataPacks = (snapshot: WorkspaceSnapshot) => snapshot.workspace.data_packs;
export const selectHealth = (snapshot: WorkspaceSnapshot) => snapshot.health;
export const selectFailures = (snapshot: WorkspaceSnapshot) => snapshot.failures;
export const selectLoaded = (snapshot: WorkspaceSnapshot) => snapshot.loaded;
export const selectOnline = (snapshot: WorkspaceSnapshot) => snapshot.online;
export const selectLauncherRequired = (snapshot: WorkspaceSnapshot) => snapshot.launcherRequired;
