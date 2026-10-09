// The route table (P1 spec 5.1) and the URL <-> workspace-location mapping.
//
// Pure functions only: the workbench (useWorkbenchState) decides when to
// navigate, the root page (app/page.tsx) forwards old /?view= links, and the
// sidebar takes its hrefs from here.  The path names the page (and the Run on
// /runs/[runId]/*); the query keeps the selection that is not a page: the
// research path, the Study, the Run outside the Run routes, the Data context and
// the research-journey data context (N-5).  A page's own state (year, period,
// stage, tab) is written by that page and survives only while the page stays.
import type { View } from "../shared/navigation.ts";
import { readWorkspaceLocation, type WorkspaceLocation, type WorkspacePath } from "../workspace/workspaceLocation.ts";

/** The views that belong to one Run: /runs/[runId] and /runs/[runId]/* (without a Run, the Run centre /runs). */
export const RUN_SECTION_VIEWS = ["run", "marketReplay", "curtailment", "networkRedispatch", "systems"] as const;
export type RunSectionView = typeof RUN_SECTION_VIEWS[number];
export const isRunSectionView = (view: View): view is RunSectionView => (RUN_SECTION_VIEWS as readonly string[]).includes(view);

const RUN_SUFFIX: Record<RunSectionView, string> = { run: "", marketReplay: "/replay", curtailment: "/vre", networkRedispatch: "/network", systems: "/systems" };
const STATIC_PATH: Record<Exclude<View, RunSectionView>, string> = {
  overview: "/", learn: "/learn", journey: "/journey", projects: "/studies", data: "/data",
  models: "/modules", extend: "/extensions", runCentre: "/runs", compare: "/compare", audit: "/inspect",
};

/** The query keys the workbench owns; every other key belongs to the page. */
export const WORKBENCH_QUERY_KEYS = ["view", "path", "study", "run", "dataContext", "journeyRevision", "journeyPack"] as const;

const identifier = (value: string | null | undefined) => value && value.length <= 256 && !/[\u0000-\u001f\u007f/]/.test(value) ? value : "";
function segment(value: string): string {
  try { return identifier(decodeURIComponent(value)); } catch { return ""; }
}

export type RouteMatch = { view: View; runId: string; studyId: string };

/** The page a path names, or null for a path that is not in the route table. */
export function matchRoute(pathname: string): RouteMatch | null {
  const parts = pathname.split("?")[0].split("/").filter(Boolean);
  const [first, second, third, ...rest] = parts;
  if (!first) return { view: "overview", runId: "", studyId: "" };
  if (first === "runs") {
    // W4c (spec 5.1): /runs is the Run centre; /runs/[runId] one Run's annual results.
    if (!second) return { view: "runCentre", runId: "", studyId: "" };
    const runId = segment(second);
    if (!runId || rest.length) return null;
    const section = (Object.entries(RUN_SUFFIX) as [RunSectionView, string][]).find(([, suffix]) => suffix === (third ? `/${third}` : ""));
    return section ? { view: section[0], runId, studyId: "" } : null;
  }
  if (first === "studies" && second) {
    const studyId = segment(second);
    return studyId && !third ? { view: "projects", runId: "", studyId } : null;
  }
  if (second) return null;
  const entry = (Object.entries(STATIC_PATH) as [View, string][]).find(([, path]) => path === `/${first}`);
  return entry ? { view: entry[0], runId: "", studyId: "" } : null;
}

/** A plain link to a page (sidebar entries). A Run page without a Run is the Run centre. */
export function viewHref(view: View): string {
  return isRunSectionView(view) ? "/runs" : STATIC_PATH[view];
}

/** The workspace selection a URL restores: the page from the path, the rest from the query. */
export type RouteLocation = Omit<WorkspaceLocation, "view"> & { view: View; editingStudyId: string };

export function readRouteLocation(pathname: string, search: string): RouteLocation {
  const query = readWorkspaceLocation(search);
  const match = matchRoute(pathname) ?? { view: "overview" as View, runId: "", studyId: "" };
  const location: RouteLocation = {
    ...query,
    view: match.view,
    runId: match.runId || query.runId,
    studyId: query.studyId || match.studyId,
    editingStudyId: match.studyId,
  };
  return location;
}

export type RouteState = {
  view: View;
  path: WorkspacePath | null;
  studyId: string;
  runId: string;
  dataContextId: string;
  journey?: { sourceRevisionSha256: string; targetPackId: string };
  /** The Study that owns runId (when known); the URL then omits ?study=. */
  runStudyId?: string;
  /** The saved Study the composer edits; /studies/[studyId]. */
  editingStudyId?: string;
};

/** Two spellings of one path (percent-encoded or not, trailing slash). */
export function samePathname(a: string, b: string): boolean {
  const normal = (value: string) => {
    let text = value.split("?")[0];
    try { text = decodeURIComponent(text); } catch { /* keep the encoded form */ }
    return text.length > 1 ? text.replace(/\/+$/, "") : text;
  };
  return normal(a) === normal(b);
}

export function routePathname(state: Pick<RouteState, "view" | "runId" | "editingStudyId">): string {
  if (isRunSectionView(state.view)) return state.runId ? `/runs/${encodeURIComponent(state.runId)}${RUN_SUFFIX[state.view]}` : "/runs";
  if (state.view === "projects" && state.editingStudyId) return `/studies/${encodeURIComponent(state.editingStudyId)}`;
  return STATIC_PATH[state.view];
}

/** R-12 (P1-polish): the pages that read the workbench's Study selection from
 * the URL (the Run pages and Data with a saved Study's data context are
 * decided in studyInQuery); every other page leaves ?study= out. */
export const STUDY_QUERY_VIEWS: readonly View[] = ["journey", "projects", "extend", "runCentre", "audit"];
/** R-12: the pages that read the selected Run from the query (a Run page has it in its path). */
export const RUN_QUERY_VIEWS: readonly View[] = ["runCentre", "audit"];

function studyInQuery(state: RouteState): boolean {
  if (isRunSectionView(state.view)) return true;
  if (state.view === "data") return state.dataContextId !== "draft" && state.dataContextId !== "journey";
  return STUDY_QUERY_VIEWS.includes(state.view);
}

/** RR-1 (1): the part of a URL the workbench owns - its path and its own
 * query keys - in one spelling (page keys such as year or tab are left out).
 * Two URLs with the same key carry the same page and selection, so a change
 * of key that the workbench did not write is a history traversal (Back,
 * Forward) whose selection is restored. */
export function workbenchUrlKey(url: string): string {
  const [rawPath, ...rest] = url.split("?");
  let path = rawPath || "/";
  try { path = decodeURIComponent(path); } catch { /* keep the encoded form */ }
  if (path.length > 1) path = path.replace(/\/+$/, "");
  const params = new URLSearchParams(rest.join("?").split("#")[0]);
  const own = WORKBENCH_QUERY_KEYS.flatMap((key) => params.getAll(key).map((value) => `${key}=${encodeURIComponent(value)}`));
  return `${path}?${own.join("&")}`;
}

export type RestoredSelection = { studyId: string; runId: string; dataContextId: string };

/** RR-1 (1): the Study, Run and data context a traversed URL restores.  The
 * URL is authoritative for what its route writes (R-12: ?study= where the page
 * reads it, ?run= on the Run centre and Inspect or in a Run page's path, the
 * data context and research path everywhere); a route that leaves ?study= or
 * ?run= out keeps the current selection instead of clearing it. */
export function restoredSelection(location: RouteLocation, current: RestoredSelection, runs: readonly { id: string; project_id: string }[]): RestoredSelection {
  const runInPath = isRunSectionView(location.view);
  const readsRun = runInPath || RUN_QUERY_VIEWS.includes(location.view);
  const readsStudy = runInPath || (location.view === "data"
    ? location.dataContextId !== "draft" && location.dataContextId !== "journey"
    : STUDY_QUERY_VIEWS.includes(location.view)) || Boolean(location.studyId);
  const linkedRun = runs.find((run) => run.id === location.runId);
  return {
    studyId: readsStudy ? location.studyId || linkedRun?.project_id || "" : current.studyId,
    runId: readsRun ? location.runId : current.runId,
    dataContextId: location.dataContextId,
  };
}

/** The URL (path and query) of a workspace state.  `keepPageQuery` keeps the
 * page's own query keys (same page); a new page starts without them.  R-12:
 * ?study= and ?run= are written only where the page reads them;
 * `allSelection` keeps both (old /?view= links hand their whole selection on). */
export function routeUrl(state: RouteState, currentSearch: string, keepPageQuery: boolean, allSelection = false): string {
  const pathname = routePathname(state);
  const params = new URLSearchParams(keepPageQuery ? currentSearch : "");
  const runInPath = isRunSectionView(state.view) && Boolean(state.runId);
  const studyImplied = (runInPath && state.runStudyId === state.studyId)
    || (state.view === "projects" && Boolean(state.editingStudyId) && state.editingStudyId === state.studyId);
  const journey = state.dataContextId === "journey" ? state.journey : undefined;
  const values: Record<(typeof WORKBENCH_QUERY_KEYS)[number], string | null | undefined> = {
    view: null,
    path: state.path,
    study: studyImplied || !(allSelection || studyInQuery(state)) ? null : state.studyId,
    run: runInPath || !(allSelection || RUN_QUERY_VIEWS.includes(state.view)) ? null : state.runId,
    dataContext: state.dataContextId === "draft" ? null : state.dataContextId,
    journeyRevision: journey?.sourceRevisionSha256,
    journeyPack: journey?.targetPackId,
  };
  for (const [key, value] of Object.entries(values)) {
    if (value) params.set(key, value);
    else params.delete(key);
  }
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}`;
}

/** Spec 5.1: an old /?view=<id> link opens the same page at its route; the
 * other parameters are kept (the Run of a Run page moves into the path).
 * Null when the query names no view. */
export function legacyRedirect(search: string): string | null {
  const params = new URLSearchParams(search);
  if (!params.has("view")) return null;
  const location = readWorkspaceLocation(search);
  const rest = new URLSearchParams(search);
  rest.delete("view");
  return routeUrl({
    view: location.view, path: location.path, studyId: location.studyId, runId: location.runId,
    dataContextId: location.dataContextId, journey: location.journey,
  }, `?${rest.toString()}`, true, true);
}

/** Search params of a Next page (string | string[] | undefined) as a query string. */
export function searchFromRecord(record: Record<string, string | string[] | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(record)) {
    if (Array.isArray(value)) for (const item of value) params.append(key, item);
    else if (value !== undefined) params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

/** Replace the current page's own query keys (year, period, stage, tab) without
 * a new history entry; empty values are removed.  Workbench keys are refused. */
export function replacePageQuery(updates: Record<string, string | number | null | undefined>): void {
  if (typeof window === "undefined") return;
  const params = new URLSearchParams(window.location.search);
  for (const [key, value] of Object.entries(updates)) {
    if ((WORKBENCH_QUERY_KEYS as readonly string[]).includes(key)) continue;
    if (value === null || value === undefined || value === "") params.delete(key);
    else params.set(key, String(value));
  }
  const query = params.toString();
  const url = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  if (url !== `${window.location.pathname}${window.location.search}${window.location.hash}`) window.history.replaceState(null, "", url);
}
