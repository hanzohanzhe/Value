export const WORKSPACE_VIEWS = ["journey", "learn", "overview", "data", "models", "projects", "run", "marketReplay", "curtailment", "networkRedispatch", "systems", "audit", "extend"] as const;
export type WorkspaceView = typeof WORKSPACE_VIEWS[number];
export type WorkspacePath = "reproduce" | "data" | "module" | "function";
export type WorkspaceLocation = { view: WorkspaceView; path: WorkspacePath | null; studyId: string; runId: string; dataContextId: string };

const paths: WorkspacePath[] = ["reproduce", "data", "module", "function"];
const identifier = (value: string | null) => value && value.length <= 256 && !/[\u0000-\u001f\u007f]/.test(value) ? value : "";

export function readWorkspaceLocation(search: string): WorkspaceLocation {
  const params = new URLSearchParams(search);
  const view = params.get("view");
  const path = params.get("path");
  return {
    view: WORKSPACE_VIEWS.includes(view as WorkspaceView) ? view as WorkspaceView : "overview",
    path: paths.includes(path as WorkspacePath) ? path as WorkspacePath : null,
    studyId: identifier(params.get("study")),
    runId: identifier(params.get("run")),
    dataContextId: identifier(params.get("dataContext")) || "draft",
  };
}

export function writeWorkspaceLocation(search: string, location: WorkspaceLocation): string {
  const params = new URLSearchParams(search);
  for (const [key, value] of Object.entries({ view: location.view, path: location.path, study: location.studyId, run: location.runId, dataContext: location.dataContextId === "draft" ? null : location.dataContextId })) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  return `?${params.toString()}`;
}

export function selectWorkspaceRun<T extends { id: string; project_id: string }>(runs: T[], studyId: string, runId: string): T | undefined {
  // An explicit missing or mismatched Run must never silently open another result.
  return runId
    ? runs.find((run) => run.id === runId && run.project_id === studyId)
    : runs.find((run) => run.project_id === studyId);
}
