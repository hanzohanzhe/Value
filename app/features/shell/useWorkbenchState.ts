// The workbench state (P1 W3, spec 5): every piece of state and every action
// that app/page.tsx's single component held, moved essentially verbatim into
// one hook.  The shell (features/shell/Workbench.tsx) mounts it once in the root
// layout, so the state survives route changes; each route's view reads it with
// useWorkbench().  The view comes from the URL path (features/shell/routes.ts).
import { applyProfileChoice, isMethodologyCatalogue, type MethodologyCatalogue } from "../studies/methodologyChoice.ts";
import { migrationFromResponse, openingMigration, type RevisionMigration } from "../studies/studyMigration.ts";
import { alignZonalSolverContract } from "../studies/solverContract";
import type { AuditTab } from "../evidence/AuditView";
import { modelDisplayName } from "../shared/presentation";
import { API_BASE, LauncherAccessError, apiFetch, getJson } from "../../lib/api.ts";
import { createPoller, serviceState, type Poller } from "../../lib/poll.ts";
import { createWorkspaceStore, selectFailures, selectHealth, selectLauncherRequired, selectLoaded, selectOnline, selectWorkspace, useWorkspaceSelector, type HealthPayload } from "../../lib/workspaceStore.ts";
import { useT } from "../../i18n/LocaleProvider";
import { errorPrefix } from "../../i18n/index.ts";
import type { QuarantineRow } from "../modules/ModuleQuarantinePanel";
import { isPendingRunsRefusal, pendingRunsQuestion, stoppedRunsNotice } from "../modules/module-quarantine.mjs";
import type { EntryError } from "../modules/DisabledEntriesPanel";
import { validationLayers, type DataPackValidationReport } from "../data/dataPackValidation.ts";
import { lifecyclePath, type DisabledEntry } from "../modules/disabledEntries.ts";
import type { View } from "../shared/navigation";
import type { Workspace } from "../shared/workspaceTypes";
import type { ModuleInstallation, Extension, ExtensionInstallation, DomainPreset, DraftResolution, StudyForm, Project, StudyTrashEntry, ParameterDefinition } from "../studies/types";
import type { RunMode, ModelRun, PreflightReport, ResourceReadiness, FrozenInputSnapshot } from "../runs/types";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CommunityPath } from "../workspace/CommunityPaths";
import { ALL_RUN_MODES, runModesForStudy, selectedRunScope } from "../workspace/runScope";
import { environmentBlockers, preflightKey, preflightMatches } from "../workspace/preflightIdentity";
import { resolveRunContext } from "../workspace/runContext";
import { journeyFromLocation, selectWorkspaceRun } from "../workspace/workspaceLocation";
import { isRunSectionView, matchRoute, readRouteLocation, restoredSelection, routeUrl, samePathname, workbenchUrlKey, type RouteLocation } from "./routes.ts";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { describeResearchSuiteInstallation, researchSuiteApiUrl } from "../data/research-suite-api.mjs";
import { defaultDraftPackId } from "../studies/draftPack.ts";
import { DEFAULT_RUNTIME_VALUES, INITIAL_DRAFT_PACK_ID, defaultStudyForm, savedStudySnapshot, stableJson, type StudyDraftSnapshot } from "../studies/studyDraft.ts";
import { useStudyDraft } from "../studies/useStudyDraft.ts";
import { latestRunFor } from "../shared/latestRun.ts";
import { saveFailureNotice, type SaveFailure } from "../studies/studySave.ts";
import { studyResolutionKey } from "../studies/studyResolutionKey.ts";
import { preparationProgressText, type StartedRunNotice } from "../runs/runHistoryView.ts";
import { VALUE_101_FALLBACK, type Value101TutorialDescriptor } from "../learn/value101";
import { buildStudyTrashConfirmation, sourceStudyAllowsDerivedRun } from "../learn/studyLifecycle";

import type { DataPreview, ResearchSuiteInstallation, ResearchSuiteSummary } from "../data/dataPageTypes.ts";
import type { ReplayTarget } from "../market/MarketReplayView";

const API = API_BASE;

const emptyWorkspace: Workspace = {
  architecture_version: "value.contracts/v2", modules: [], module_slots: [], extensions: [], dataset_slots: [], data_packs: [],
  module_installations: [], extension_installations: [], projects: [], study_trash: [], runs: [], runtime: { python: "", compatible: false },
};
// The sidebar entries and their dictionary keys live in features/shared/navigation.ts (P1 spec 3).

/** An Enable/Remove refusal with its backend code (spec 11.4). */
class EntryLifecycleError extends Error {
  constructor(message: string, readonly code?: string) { super(message); }
}

export function useWorkbenchState() {
  // P1 W3 (spec 5.1): the page is the URL path.  setView asks for a page; the
  // navigation effect below moves the URL there once the state set by the same
  // action (Study, Run, data context) is committed.  Until the path names the
  // requested page, `view` is the requested one, so the rail and the title move
  // at once.  Server rendering reads the same URL, so a deep link renders its
  // own page first (F1-09) and the selection needs no deferred read.
  const pathname = usePathname() ?? "/";
  const searchParams = useSearchParams();
  const router = useRouter();
  const routerSearch = searchParams?.toString() ?? "";
  const [initialLocation] = useState(() => readRouteLocation(pathname, `?${routerSearch}`));
  const routedView: View = matchRoute(pathname)?.view ?? "overview";
  // A request belongs to the path it was made on: once the path changes (the
  // page opened, or Back/Forward), the path names the page again.
  const [navRequest, setNavRequest] = useState<{ view: View; from: string } | null>(null);
  const setView = useCallback((next: View) => setNavRequest({ view: next, from: pathname }), [pathname]);
  const [activePath, setActivePath] = useState<CommunityPath | null>(initialLocation.path);
  const [readMeOpen, setReadMeOpen] = useState(false);
  const pendingLocation = useRef<RouteLocation | null>(initialLocation);
  // /studies/[studyId]: the saved Study the composer opens once the workspace is loaded.
  const pendingStudyEdit = useRef(initialLocation.view === "projects" ? initialLocation.editingStudyId : "");
  const replaceLocation = useRef(true);
  const pendingNavigation = useRef("");
  const t = useT();
  // P1 spec 4: the workspace and the service state live in one external store
  // (lib/workspaceStore.ts); polls are merged by structural sharing, so an
  // unchanged Study or Run keeps its object identity (F1-01).
  const [store] = useState(() => createWorkspaceStore(emptyWorkspace));
  const workspace = useWorkspaceSelector(selectWorkspace, { store });
  const [definitions, setDefinitions] = useState<ParameterDefinition[]>([]);
  const online = useWorkspaceSelector(selectOnline, { store });
  const launcherRequired = useWorkspaceSelector(selectLauncherRequired, { store });
  // P0-3 S8: the rail shows degraded after a failure or a degraded health
  // status, and offline only after OFFLINE_AFTER_FAILURES consecutive failures.
  const refreshFailures = useWorkspaceSelector(selectFailures, { store });
  const workspaceLoaded = useWorkspaceSelector(selectLoaded, { store });
  const health = useWorkspaceSelector(selectHealth, { store });
  const connectionState = serviceState(refreshFailures, health?.status, workspaceLoaded);
  const [selectedPackId, setSelectedPackId] = useState(INITIAL_DRAFT_PACK_ID);
  const [selectedProjectId, setSelectedProjectId] = useState(initialLocation.studyId);
  const [selectedRunId, setSelectedRunId] = useState(initialLocation.runId);
  const [selectedRunDetail, setSelectedRunDetail] = useState<ModelRun | null>(null);
  const [uploading, setUploading] = useState("");
  const [dataBundle, setDataBundle] = useState<File | null>(null);
  const [dataRights, setDataRights] = useState(false);
  const [dataInstalling, setDataInstalling] = useState(false);
  const [dataInstallProgress, setDataInstallProgress] = useState(0);
  const [dataInstallPhase, setDataInstallPhase] = useState<"idle" | "uploading" | "verifying">("idle");
  const dataInstallRequest = useRef<XMLHttpRequest | null>(null);
  const [researchSuiteBundle, setResearchSuiteBundle] = useState<File | null>(null);
  const [researchSuiteRights, setResearchSuiteRights] = useState(false);
  const [researchSuiteInstalling, setResearchSuiteInstalling] = useState(false);
  const [researchSuiteInstallProgress, setResearchSuiteInstallProgress] = useState(0);
  const [researchSuiteInstallPhase, setResearchSuiteInstallPhase] = useState<"idle" | "uploading" | "verifying">("idle");
  const [researchSuiteSummary, setResearchSuiteSummary] = useState<ResearchSuiteSummary | null>(null);
  const researchSuiteInstallRequest = useRef<XMLHttpRequest | null>(null);
  const [moduleBundle, setModuleBundle] = useState<File | null>(null);
  // M-D9 / F-D6 (round R1-5): a successful install also clears the native file input.
  const [bundleInputGeneration, setBundleInputGeneration] = useState(0);
  const [moduleTrust, setModuleTrust] = useState(false);
  const [moduleInstalling, setModuleInstalling] = useState(false);
  const [moduleLifecycle, setModuleLifecycle] = useState("");
  const [extensionBundle, setExtensionBundle] = useState<File | null>(null);
  const [extensionTrust, setExtensionTrust] = useState(false);
  const [extensionInstalling, setExtensionInstalling] = useState(false);
  const [extensionLifecycle, setExtensionLifecycle] = useState("");
  const [launching, setLaunching] = useState("");
  const [replayTarget, setReplayTarget] = useState<ReplayTarget | null>(null);
  // "Show stress events" (spec 2.3 notice 4): open Market replay at the full-year stress-event list (spec 4.4).
  const [stressEventsFocus, setStressEventsFocus] = useState(0);
  const [inspectTarget, setInspectTarget] = useState<{ tab: AuditTab; nonce: number } | null>(null);
  // R3-N3 (round R2): a requested Inspect tab is used once; ordinary navigation opens Inspect on its own default tab.
  const openView = (next: View) => { setInspectTarget(null); setView(next); };
  // Spec 7 / X0 S12: methodology catalogue for the Study composer, and the pending migration confirmation.
  const [methodologyCatalogue, setMethodologyCatalogue] = useState<MethodologyCatalogue | null>(null);
  const [methodologyError, setMethodologyError] = useState("");
  const [migrationPrompt, setMigrationPrompt] = useState<{ projectId: string; studyName?: string; migration: RevisionMigration; nonce: number } | null>(null);
  // S-D12: null until the user picks a scope; until then "Check for" follows the selected Run.
  const [preflightMode, setPreflightMode] = useState<RunMode | null>(null);
  const [storedPreflight, setPreflight] = useState<PreflightReport | null>(null);
  const [pendingPreflightKey, setPendingPreflightKey] = useState<string | null>(null);
  const preflightRequest = useRef(0);
  const [notice, setNotice] = useState("");
  // S-D12 / M2-N1: the start notice follows its Run to completion or failure.
  const [startedRun, setStartedRun] = useState<StartedRunNotice | null>(null);
  const [parameterValues, setParameterValues] = useState<Record<string, unknown>>({});
  const [runtimeValues, setRuntimeValues] = useState<Record<string, unknown>>(() => ({ ...DEFAULT_RUNTIME_VALUES }));
  const [resolvedSources, setResolvedSources] = useState<Record<string, { source?: string }>>({});
  // The draft's resolution is keyed by the draft it answers (P1 W4a, D-W3-14):
  // an edit shows "resolving" at once without resetting state in an effect.
  const [draftResult, setDraftResult] = useState<{ key: string; resolution: DraftResolution | null; error: string } | null>(null);
  const [composerInitialStep, setComposerInitialStep] = useState(1);
  const [draftPackCopyName, setDraftPackCopyName] = useState("");
  const [copyingDraftPack, setCopyingDraftPack] = useState(false);
  const [dataContextId, setDataContextId] = useState(initialLocation.dataContextId);
  // N-5 (round R1-5): a reload of the journey Data page restores its source revision and target pack.
  const [journeyTargetPackId, setJourneyTargetPackId] = useState(() => journeyFromLocation(initialLocation)?.targetPackId ?? "");
  const [journeyData, setJourneyData] = useState<{ sourceStudyId: string; sourceRevisionSha256: string; targetPackId: string } | null>(() => journeyFromLocation(initialLocation));
  const dataPreviewRequest = useRef(0);
  // S-F-中1 (R5): keyed by the Study's content, not its object identity, so a
  // workspace poll during a Run (new objects, same Study) keeps the resolution
  // and the mapping editor's staged file.
  const [savedDataResolution, setSavedDataResolution] = useState<{ key: string; manifestSha256?: string; resolution: DraftResolution } | null>(null);
  const [dataPreviewResult, setDataPreview] = useState<{ contextId: string; packId: string; manifestSha256?: string; preview: DataPreview } | null>(null);
  const [dataPreviewLoading, setDataPreviewLoading] = useState("");
  const [domainExtensionIds, setDomainExtensionIds] = useState<string[]>([]);
  const [editingBaseRevision, setEditingBaseRevision] = useState<string | undefined>();
  const leaveStudyEditRef = useRef<() => void>(() => {});
  /** R-15: the routed path the URL effect last saw ("" before its first run): a move of the router is told from our own edits by it. */
  const lastRoutedPath = useRef("");
  const [editingProjectId, setEditingProjectId] = useState<string | undefined>();
  const [frozenRunReadiness, setFrozenRunReadiness] = useState<ResourceReadiness | null>(null);
  const [frozenRunProject, setFrozenRunProject] = useState<Project | null>(null);
  const [frozenInputSnapshot, setFrozenInputSnapshot] = useState<FrozenInputSnapshot | null>(null);
  const [frozenRunSelectionId, setFrozenRunSelectionId] = useState("");
  const [value101Tutorial, setValue101Tutorial] = useState<Value101TutorialDescriptor>(VALUE_101_FALLBACK);
  const [value101Loading, setValue101Loading] = useState(true);
  const [value101Error, setValue101Error] = useState("");
  const [projectForm, setProjectForm] = useState<StudyForm>(() => defaultStudyForm());
  // F4-03: one save at a time; the Save button shows it.
  const [savingStudy, setSavingStudy] = useState(false);
  const savingStudyRef = useRef(false);
  /** Puts a Study draft into the composer (Edit, the extension draft, Restore unsaved draft). */
  const applyStudySnapshot = useCallback((snapshot: StudyDraftSnapshot) => {
    setSelectedPackId(snapshot.packId);
    setProjectForm(snapshot.form);
    setParameterValues({ ...snapshot.parameters });
    setRuntimeValues({ ...snapshot.runtime });
  }, []);

  // P1 spec 4 (lib/poll.ts): one workspace read in flight at a time; a refresh
  // after an action waits for a poll in flight and then reads again. Polls run
  // while a Run is active or the service is failing (2 s, then 4, 8, 16, 30 s),
  // pause while the tab is hidden and refresh at once when it is shown.
  const pollerRef = useRef<Poller<Workspace> | null>(null);
  useEffect(() => {
    const poller = createPoller<Workspace>({
      read: (signal) => getJson<Workspace>(`${API}/workspace`, signal),
      onData: (next) => {
        store.receiveWorkspace({
          ...next,
          module_installations: next.module_installations ?? [],
          extension_installations: next.extension_installations ?? [],
          study_trash: next.study_trash ?? [],
          module_slots: next.module_slots ?? [],
          extensions: (next.extensions ?? []).map((extension) => ({ ...extension, name: modelDisplayName(extension.name) })),
          data_packs: next.data_packs.map((pack) => ({ ...pack, name: modelDisplayName(pack.name) })),
          modules: next.modules.map((module) => ({ ...module, name: modelDisplayName(module.name), description: modelDisplayName(module.description) })),
          projects: next.projects.map((project) => ({ ...project, name: modelDisplayName(project.name) })),
          runs: next.runs.map((run) => ({ ...run, project_name: modelDisplayName(run.project_name) })),
        });
        void getJson<HealthPayload>(`${API}/health`).then((payload) => store.update({ health: payload })).catch(() => store.update({ health: null }));
        // R4 R-低6: a recovered or overlay pack is never the default selection.
        setSelectedPackId((current) => defaultDraftPackId(next.data_packs, current));
        const requestedRunId = pendingLocation.current?.runId;
        const requestedRun = next.runs.find((run) => run.id === requestedRunId);
        // Keep explicit identities, even when unavailable. Never silently replace a shared Run link.
        setSelectedProjectId((current) => current || requestedRun?.project_id || next.projects[0]?.id || "");
        pendingLocation.current = null;
      },
      // The last workspace stays on screen (readable); actions that need the
      // service are disabled while it is not online.
      onError: (error, failures) => {
        if (error instanceof LauncherAccessError) store.update({ launcherRequired: true });
        else store.update({ online: false, failures });
      },
      fatal: (error) => error instanceof LauncherAccessError,
      shouldPoll: () => store.getSnapshot().workspace.runs.some((run) => ["queued", "snapshotting", "running", "cancel_requested"].includes(run.status)),
    });
    pollerRef.current = poller;
    poller.start();
    return () => { poller.stop(); if (pollerRef.current === poller) pollerRef.current = null; };
  }, [store]);
  const refresh = useCallback((): Promise<Workspace | null> => pollerRef.current?.refresh() ?? Promise.resolve(null), []);
  const refreshValue101Tutorial = useCallback(async () => {
    setValue101Loading(true);
    setValue101Error("");
    try {
      setValue101Tutorial(await getJson<Value101TutorialDescriptor>(`${API}/tutorials/value-101`));
    } catch (reason) {
      setValue101Tutorial(VALUE_101_FALLBACK);
      setValue101Error(reason instanceof Error ? reason.message : t("workbench.tutorialUnavailable"));
    } finally {
      setValue101Loading(false);
    }
  }, [t]);
  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
      void refreshValue101Tutorial();
      void getJson<{ parameters: ParameterDefinition[] }>(`${API}/parameters`)
        .then((payload) => setDefinitions(payload.parameters)).catch(() => undefined);
      void getJson<unknown>(`${API}/methodology/profiles`)
        .then((payload) => { if (isMethodologyCatalogue(payload)) { setMethodologyCatalogue(payload); setMethodologyError(""); } else setMethodologyError("unexpected catalogue format"); })
        .catch((reason: unknown) => setMethodologyError(reason instanceof Error ? reason.message : "catalogue unavailable"));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh, refreshValue101Tutorial]);
  const projectRuns = useMemo(
    () => workspace.runs.filter((run) => run.project_id === selectedProjectId),
    [selectedProjectId, workspace.runs],
  );
  const selectedRunSummary = selectWorkspaceRun(workspace.runs, selectedProjectId, selectedRunId);
  const locationRunId = selectedRunId || selectedRunSummary?.id || "";
  const locationRunStudyId = workspace.runs.find((run) => run.id === locationRunId)?.project_id;
  // The page shown: the requested one while its navigation is under way, else
  // the routed one.  A Run page asked for without a Run is the Run centre (/runs, W4c).
  const resolvedRequest: View | null = navRequest ? (isRunSectionView(navRequest.view) && !locationRunId ? "runCentre" : navRequest.view) : null;
  // A request ends when the path changes (its page opened, or Back/Forward) or
  // when it names the page already shown; it must not come back to life when
  // Back returns to the path it was made on.
  if (navRequest && (navRequest.from !== pathname || resolvedRequest === routedView)) setNavRequest(null);
  const requestedView: View | null = navRequest && navRequest.from === pathname ? resolvedRequest : null;
  const view: View = requestedView ?? routedView;
  // S-D10: the page a launch started from; a Run that finishes starting does not pull the user back.
  const viewRef = useRef<View>(view);
  useEffect(() => { viewRef.current = view; }, [view]);
  useEffect(() => {
    if (!selectedRunSummary) return;
    let current = true;
    void getJson<ModelRun>(`${API}/runs/${selectedRunSummary.id}`)
      .then((run) => { if (current) setSelectedRunDetail({ ...run, project_name: modelDisplayName(run.project_name) }); })
      .catch(() => { if (current) setSelectedRunDetail(null); });
    return () => { current = false; };
  }, [selectedRunSummary]);
  // R-D6 / S-D11: the input snapshot is read once per Run, after the Run has
  // left queued/snapshotting (not on every workspace poll), and the optional
  // resource-readiness file only when the snapshot records it.
  const frozenRunId = selectedRunSummary?.id ?? "";
  const frozenSnapshotWritten = Boolean(selectedRunSummary) && !["queued", "snapshotting"].includes(selectedRunSummary?.status ?? "");
  useEffect(() => {
    if (!frozenRunId || !frozenSnapshotWritten) return;
    let active = true;
    const artifact = `${API}/runs/${frozenRunId}/artifacts/input-snapshot`;
    void Promise.all([
      getJson<Project>(`${artifact}/project.json`).catch(() => null),
      getJson<FrozenInputSnapshot>(`${artifact}/snapshot.json`).catch(() => null),
    ]).then(async ([project, snapshot]) => {
      const readiness = snapshot?.resource_readiness_path === "resource-readiness.json"
        ? await getJson<ResourceReadiness>(`${artifact}/resource-readiness.json`).catch(() => null) : null;
      if (!active) return;
      setFrozenRunReadiness(readiness); setFrozenRunProject(project); setFrozenInputSnapshot(snapshot); setFrozenRunSelectionId(frozenRunId);
    });
    return () => { active = false; };
  }, [frozenRunId, frozenSnapshotWritten]);
  const hasActiveRun = workspace.runs.some((run) => ["queued", "snapshotting", "running", "cancel_requested"].includes(run.status));
  const activeRunCount = workspace.runs.filter((run) => ["queued", "snapshotting", "running", "cancel_requested"].includes(run.status)).length;
  // Poll while a Run is active or the service is failing: every 2 s, doubling
  // after each consecutive failure up to 30 s (P0-3 S8). The poller reads the
  // schedule itself after each answer; a Run started here starts polling now.
  useEffect(() => { pollerRef.current?.reschedule(); }, [hasActiveRun]);

  const selectedPack = useMemo(() => workspace.data_packs.find((pack) => pack.id === selectedPackId) ?? workspace.data_packs.find((pack) => pack.id === defaultDraftPackId(workspace.data_packs, selectedPackId)), [selectedPackId, workspace.data_packs]);
  const selectedProject = workspace.projects.find((project) => project.id === selectedProjectId);
  const selectedProjectPack = workspace.data_packs.find((pack) => pack.id === selectedProject?.data_pack_id);
  const allowedStudyModes = runModesForStudy(selectedProject, selectedProjectPack);
  const canRunMode = (mode: RunMode) => allowedStudyModes.includes(mode);
  const effectivePreflightMode = selectedRunScope(preflightMode ?? selectedRunSummary?.mode ?? "smoke", allowedStudyModes);
  const currentPreflightKey = effectivePreflightMode ? preflightKey(selectedProject, effectivePreflightMode) : null;
  const checkingPreflight = Boolean(currentPreflightKey && pendingPreflightKey === currentPreflightKey);
  const preflight = effectivePreflightMode && preflightMatches(storedPreflight, selectedProject, effectivePreflightMode) ? storedPreflight : null;
  function selectRunProject(projectId: string) {
    const nextProject = workspace.projects.find((project) => project.id === projectId);
    const nextPack = workspace.data_packs.find((pack) => pack.id === nextProject?.data_pack_id);
    setSelectedProjectId(projectId);
    setSelectedRunId("");
    setPreflight(null);
    const nextModes = runModesForStudy(nextProject, nextPack);
    if (preflightMode && !nextModes.includes(preflightMode) && nextModes.length) {
      setPreflightMode(selectedRunScope(preflightMode, nextModes)!);
    }
  }
  const zonalPreflight = preflight?.checks?.domain_readiness?.sections.zonal_network;
  const selectedRun = selectedRunDetail && selectedRunDetail.id === selectedRunSummary?.id ? selectedRunDetail : selectedRunSummary;
  const selectedRunSourceMutable = sourceStudyAllowsDerivedRun(selectedRun?.source_study_status);
  const isRunView = ["runCentre", "run", "marketReplay", "curtailment", "networkRedispatch", "systems", "audit"].includes(view);
  const selectedRunContext = resolveRunContext({ run: selectedRun, frozen: {
    runId: frozenRunSelectionId,
    status: frozenRunSelectionId === selectedRun?.id ? frozenRunProject ? "ready" : "unavailable" : "loading",
    project: frozenRunProject, snapshot: frozenInputSnapshot,
  } });

  // RR-1 (1), D-P1P-6: Back and Forward restore the selection from the
  // router's URL.  A popstate listener was never called on a real traversal
  // (vinext re-renders the shell inside the same event and the listener, which
  // depended on setView, was removed during dispatch), so the restoration is
  // driven by the router's pathname and query instead: when the workbench's
  // part of the URL changes to something the workbench did not write itself,
  // the history moved and the URL's Study, Run, data context and research path
  // are applied.  The URL effect below skips its write in that same commit.
  const urlKey = workbenchUrlKey(`${pathname}?${routerSearch}`);
  /** The workbench part of the URL the state was last in step with. */
  const syncedUrlKey = useRef(urlKey);
  /** URLs the workbench wrote that the router has not reported yet. */
  const ownUrlWrites = useRef<string[]>([]);
  /** Set by a restoration; the URL effect of the same commit writes nothing. */
  const restoringLocation = useRef(false);
  const restoreRef = useRef<(location: RouteLocation) => void>(() => {});
  useEffect(() => {
    restoreRef.current = (location) => {
      const selection = restoredSelection(location, { studyId: selectedProjectId, runId: selectedRunId, dataContextId }, workspace.runs);
      replaceLocation.current = true;
      restoringLocation.current = true;
      setActivePath(location.path);
      setSelectedProjectId(selection.studyId);
      setSelectedRunId(selection.runId);
      setDataContextId(selection.dataContextId);
      const journey = journeyFromLocation(location);
      if (journey) { setJourneyData(journey); setJourneyTargetPackId(journey.targetPackId); }
      setReadMeOpen(false);
    };
  });
  useEffect(() => {
    if (urlKey === syncedUrlKey.current) return;
    syncedUrlKey.current = urlKey;
    const own = ownUrlWrites.current.indexOf(urlKey);
    if (own >= 0) { ownUrlWrites.current = ownUrlWrites.current.slice(own + 1); return; }
    ownUrlWrites.current = [];
    restoreRef.current(readRouteLocation(pathname, `?${routerSearch}`));
  }, [pathname, routerSearch, urlKey]);

  // P1 W3 (spec 5.1, principle 0.3): the URL follows the workspace.  A new page
  // is a router navigation (its route renders); the same page with another
  // Study, Run or data context only rewrites the URL (the page stays mounted).
  // The selection is written once the workspace is loaded (an explicit link is
  // never rewritten before its Study and Run are known); a requested page is
  // opened at once.
  useEffect(() => {
    // RR-1 (1): a restoration made in this commit is consumed here, whichever way this run ends.
    const restoring = restoringLocation.current;
    restoringLocation.current = false;
    if (requestedView === null && connectionState === "loading") return;
    // While the router is between two paths (a navigation of ours, or Back and
    // Forward, which restoreLocation applies), nothing is written: the state of
    // the old path must not overwrite the new URL.
    if (!samePathname(window.location.pathname, pathname)) return;
    // R-15 (P1-polish, ruling on D-W4a-11): the router moved between /studies
    // and /studies/[id] by itself (Back, Forward) - follow it instead of writing
    // the edit state back: /studies after the edited Study's path leaves the
    // edit (its unsaved draft stays stored under the Study and is offered when
    // it is opened again); /studies/[id] of a saved Study that is not the one
    // being edited opens it.  Our own moves change the edit state first, so
    // they never meet this case.
    const routed = matchRoute(pathname);
    const editing = editingProjectId ?? "";
    const routerLeftEdit = routed?.view === "projects" && !routed.studyId && Boolean(editing)
      && samePathname(lastRoutedPath.current, `/studies/${encodeURIComponent(editing)}`);
    const routerOpenedEdit = routed?.view === "projects" && Boolean(routed.studyId) && routed.studyId !== editing
      && !samePathname(lastRoutedPath.current, pathname) && workspace.projects.some((project) => project.id === routed.studyId);
    lastRoutedPath.current = pathname;
    if (routerLeftEdit) { leaveStudyEditRef.current(); return; }
    if (routerOpenedEdit) { pendingStudyEdit.current = routed?.studyId ?? ""; return; }
    // RR-1 (1): Back/Forward restored the selection from this URL in this
    // commit; the state still holds the previous entry's, so nothing is written.
    if (restoring) return;
    // A path outside the route table (the not-found page) keeps its URL until a page is asked for.
    if (requestedView === null && !matchRoute(window.location.pathname)) return;
    const current = `${window.location.pathname}${window.location.search}`;
    const samePage = (matchRoute(window.location.pathname)?.view ?? "overview") === view;
    const target = routeUrl({
      view, path: activePath, studyId: selectedProjectId, dataContextId,
      runId: locationRunId, runStudyId: locationRunStudyId, editingStudyId: editingProjectId,
      journey: journeyData ? { sourceRevisionSha256: journeyData.sourceRevisionSha256, targetPackId: journeyData.targetPackId } : undefined,
    }, window.location.search, samePage);
    const targetView = matchRoute(target)?.view ?? "overview";
    // P1 W4a: a new path on the same page (/studies -> /studies/[id] after a
    // save or Edit) is a router navigation too; rewriting it with history would
    // leave the router's pathname behind, and every later page request would
    // wait for the two to agree.
    const pageChanges = targetView !== routedView || !samePathname(target, window.location.pathname);
    if (pendingNavigation.current && !pageChanges) pendingNavigation.current = "";
    if (target !== current && target !== pendingNavigation.current) {
      // RR-1 (1): the router reports this URL later; it is ours, not a traversal.
      ownUrlWrites.current = [...ownUrlWrites.current, workbenchUrlKey(target)].slice(-8);
      if (pageChanges) {
        pendingNavigation.current = target;
        if (replaceLocation.current) router.replace(target);
        else router.push(target);
      } else {
        const url = `${target}${window.location.hash}`;
        if (replaceLocation.current) window.history.replaceState(null, "", url);
        else window.history.pushState(null, "", url);
      }
    }
    replaceLocation.current = false;
  }, [activePath, connectionState, dataContextId, editingProjectId, journeyData, locationRunId, locationRunStudyId, pathname, requestedView, routedView, router, routerSearch, selectedProjectId, view, workspace.projects]);

  // /studies/[studyId] opens that saved Study in the composer, as Edit does.
  useEffect(() => {
    const studyId = pendingStudyEdit.current;
    if (!studyId || !workspaceLoaded) return;
    pendingStudyEdit.current = "";
    const project = workspace.projects.find((item) => item.id === studyId);
    if (project && editingProjectId !== project.id) loadProjectRevision(project);
  });

  function chooseCommunityPath(path: CommunityPath) {
    setActivePath(path);
    if (path === "reproduce" || path === "data") setView("journey");
    // P1 W3: the extension catalogue and its author workbench are on /extensions (spec 5.1).
    else setView(path === "function" ? "extend" : "models");
  }

  // Scrolls once the routed page (not only the requested one) is rendered.
  useEffect(() => {
    const target = routedView === "models" && activePath === "module" ? "module-author-workbench"
      : routedView === "extend" && activePath === "function" ? "extension-author-workbench" : "";
    if (!target) return;
    // RR-1 (3): after the router's own scroll to the top of the new page (a
    // microtask after the commit), so the author tools stay in view.
    const frame = window.requestAnimationFrame(() => document.getElementById(target)?.scrollIntoView({ block: "start" }));
    return () => window.cancelAnimationFrame(frame);
  }, [activePath, routedView]);
  const value101Project = workspace.projects.find((project) => project.id === "value-101-baseline");
  const value101Trash = workspace.study_trash.find((entry) => entry.study_id === "value-101-baseline");
  // F4-07: "the" lesson Run is the latest one created (the list is ordered by last update).
  const value101DayRun = latestRunFor(workspace.runs, value101Project?.id, "value_101_day");
  const value101AnnualRun = latestRunFor(workspace.runs, value101Project?.id, "two_year");
  // A24-5 / L-4: Learn shows the preparation of its lesson Runs (stage and elapsed time).
  const value101Preparations = workspace.runs
    .filter((run) => run.project_id === value101Project?.id || run.project_id === "value-101-network-copperplate" || run.project_id === "value-101-network-constrained")
    .flatMap((run) => {
      const text = preparationProgressText(run);
      if (!text) return [];
      const label = t(run.project_id === "value-101-network-copperplate" ? "learn.preparation.copperplate" : run.project_id === "value-101-network-constrained" ? "learn.preparation.constrained" : run.mode === "value_101_day" ? "learn.preparation.day" : run.mode === "two_year" ? "learn.preparation.twoYear" : "learn.preparation.lesson");
      return [{ id: run.id, label, text }];
    });
  const teachingProject = Boolean(selectedProject?.extensions?.value_101);
  const readyModules = workspace.modules.filter((module) => module.status === "ready").length;
  // R5-3 低6: experimental modules are counted in the total but are never "ready"; the badge says so.
  const experimentalModules = workspace.modules.filter((module) => module.status === "experimental").length;

  // AF-低2 (P1 spec 6.2): unsaved Study drafts survive a reload (localStorage, keyed by Study ID).
  const studyDraft = useStudyDraft({
    form: projectForm, parameters: parameterValues, runtime: runtimeValues, packId: selectedPackId,
    editingProjectId, editingBaseRevision, projects: workspace.projects, packs: workspace.data_packs, workspaceLoaded, apply: applyStudySnapshot,
  });
  const draftPackManifest = selectedPack?.manifest_sha256;
  // The request the draft needs now; its answer is shown only while it still matches.
  const draftRequestBody = useMemo(() => selectedPackId && online ? JSON.stringify({
    schema_version: "value.study-draft/v1", ...projectForm,
    data_pack_id: selectedPackId, parameters: parameterValues,
    runtime_options: runtimeValues,
  }) : "", [online, parameterValues, projectForm, runtimeValues, selectedPackId]);
  const draftRequestKey = draftRequestBody ? stableJson([draftRequestBody, draftPackManifest]) : "";
  const draftAnswer = draftResult && draftResult.key === draftRequestKey ? draftResult : null;
  const draftResolution = draftAnswer?.resolution ?? null;
  const draftResolutionError = draftAnswer?.error ?? "";
  const draftResolving = Boolean(draftRequestKey) && !draftAnswer;
  /** Drop the current answer (Data page: the draft's pack changed); the draft is resolved again. */
  const setDraftResolution = useCallback((resolution: null) => setDraftResult(resolution), []);
  useEffect(() => {
    if (!draftRequestKey) return;
    let active = true;
    const timer = window.setTimeout(() => {
      void apiFetch(`${API}/projects/resolve-draft`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: draftRequestBody,
      }).then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || t("workbench.draftResolutionFailed"));
        if (active) setDraftResult({ key: draftRequestKey, resolution: payload as DraftResolution, error: "" });
      }).catch((reason: Error) => {
        if (active) setDraftResult({ key: draftRequestKey, resolution: null, error: reason.message });
      });
    }, 220);
    return () => { active = false; window.clearTimeout(timer); };
  }, [draftRequestBody, draftRequestKey, t]);

  const journeySource = workspace.projects.find((project) => project.id === journeyData?.sourceStudyId);
  const journeySourceCurrent = Boolean(journeySource && journeySource.revision_sha256 === journeyData?.sourceRevisionSha256);
  const journeySourcePack = workspace.data_packs.find((pack) => pack.id === journeySource?.data_pack_id);
  const isJourneyData = dataContextId === "journey";
  const dataContextProject = useMemo(() => isJourneyData
    ? journeySourceCurrent && journeySource && journeyData?.targetPackId
      ? { ...journeySource, data_pack_id: journeyData.targetPackId } : undefined
    : dataContextId === "draft" ? undefined : workspace.projects.find((item) => item.id === dataContextId),
  [dataContextId, isJourneyData, journeyData, journeySource, journeySourceCurrent, workspace.projects]);
  const dataContextPackId = isJourneyData ? journeyData?.targetPackId ?? ""
    : dataContextId === "draft" ? selectedPackId : dataContextProject?.data_pack_id ?? "";
  const dataContextPack = workspace.data_packs.find((item) => item.id === dataContextPackId);
  const dataManifestSha256 = dataContextPack?.manifest_sha256;
  const journeyNetworkPackId = journeySource?.market_configuration?.network_pack_id;
  // P1 W4b: the swap-data editor's read-only reasons come from the dictionaries (journeyData.readOnly.*).
  const journeyReadOnlyReason = !online ? t("journeyData.readOnly.offline")
    : !journeyData ? t("journeyData.readOnly.contextLost")
    : !journeySourceCurrent ? t("journeyData.readOnly.baselineChanged")
    : !dataContextPack ? t("journeyData.readOnly.noTarget")
    : dataContextPack.id === journeySource?.data_pack_id ? t("journeyData.readOnly.baselinePack")
    : dataContextPack.data_pack_type === "network_overlay" ? t("journeyData.readOnly.overlay")
    : workspace.projects.some((project) => project.data_pack_id === dataContextPack.id)
      ? t("journeyData.readOnly.referenced")
    : !dataManifestSha256 ? t("journeyData.readOnly.noRevision") : "";

  const dataContextKey = useMemo(() => studyResolutionKey(dataContextProject), [dataContextProject]);
  useEffect(() => {
    if (!dataContextKey) return;
    let active = true;
    void apiFetch(`${API}/projects/resolve-draft`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: dataContextKey,
    }).then(async (response) => {
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || t("workbench.dataResolutionFailed"));
      if (active) setSavedDataResolution({ key: dataContextKey, manifestSha256: dataManifestSha256, resolution: payload as DraftResolution });
    }).catch((reason: Error) => { if (active) { setSavedDataResolution(null); setNotice(reason.message); } });
    return () => { active = false; };
  }, [dataContextKey, dataManifestSha256, t]);

  const dataContextResolution = dataContextId === "draft" ? draftResolution
    : dataContextKey && savedDataResolution?.key === dataContextKey && savedDataResolution?.manifestSha256 === dataManifestSha256 ? savedDataResolution?.resolution : null;
  const activeDataSlots = dataContextResolution?.active_dataset_slots ?? workspace.dataset_slots;
  const dataGroups = [...new Set(activeDataSlots.map((slot) => slot.group))];
  const dataContextExtensions = dataContextId === "draft" ? projectForm.selected_extensions
    : dataContextProject?.selected_extensions ?? [];
  const dataPreview = dataPreviewResult?.contextId === dataContextId && dataPreviewResult.packId === dataContextPackId
    && dataPreviewResult.manifestSha256 === dataManifestSha256 ? dataPreviewResult.preview : null;
  // Spec 11.2 (S-D2): the three validation layers of the data pack in context.
  const [packValidationResult, setPackValidationResult] = useState<{ key: string; report: DataPackValidationReport | null; error: string } | null>(null);
  const [packValidationNonce, setPackValidationNonce] = useState(0);
  const packValidationPackId = view === "data" && dataContextPack?.manifest_sha256 ? dataContextPack.id : "";
  const packValidationExtensions = dataContextExtensions.join(",");
  const packValidationKey = packValidationPackId ? JSON.stringify([packValidationPackId, dataContextPack?.manifest_sha256, packValidationExtensions, packValidationNonce]) : "";
  const packValidationCurrent = packValidationResult?.key === packValidationKey ? packValidationResult : null;
  const packValidationLayers = validationLayers(packValidationCurrent?.report, dataContextPack?.plausibility_status);
  useEffect(() => {
    if (!packValidationKey) return;
    const controller = new AbortController();
    apiFetch(`${API}/data-packs/${encodeURIComponent(packValidationPackId)}/validation?extensions=${encodeURIComponent(packValidationExtensions)}`, { signal: controller.signal })
      .then(async (response) => {
        const payload = await response.json() as DataPackValidationReport & { error?: string };
        if (!response.ok) throw new Error(payload.error || `HTTP ${response.status}`);
        setPackValidationResult({ key: packValidationKey, report: payload, error: "" });
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setPackValidationResult({ key: packValidationKey, report: null, error: reason instanceof Error ? reason.message : t("workbench.validationFailed") }); });
    return () => controller.abort();
  }, [packValidationKey, packValidationPackId, packValidationExtensions, t]);

  async function previewDataRole(role: string) {
    const packId = dataContextPackId;
    const request = ++dataPreviewRequest.current;
    setDataPreviewLoading(role); setDataPreview(null);
    try {
      const preview = await getJson<DataPreview>(`${API}/data-packs/${encodeURIComponent(packId)}/preview?role=${encodeURIComponent(role)}`);
      if (request === dataPreviewRequest.current) setDataPreview({ contextId: dataContextId, packId, manifestSha256: dataManifestSha256, preview });
    } catch (reason) { if (request === dataPreviewRequest.current) setNotice(reason instanceof Error ? reason.message : t("data.notice.previewFailed")); }
    finally { if (request === dataPreviewRequest.current) setDataPreviewLoading(""); }
  }

  function chooseDomain(preset: DomainPreset) {
    setProjectForm((current) => {
      const optional = current.selected_extensions.filter((id) => !domainExtensionIds.includes(id));
      const modules = { ...current.modules, ...preset.recommended_modules };
      const zonal = modules.balancing === "value-zonal-redispatch-balancing";
      return alignZonalSolverContract({
        ...current,
        selected_extensions: [...new Set([...optional, ...preset.required_extensions])],
        market_configuration: {
          ...current.market_configuration,
          zonal_demand_mode: zonal
            ? (current.market_configuration.zonal_demand_mode || "scenario_scaled_zonal_shares")
            : "",
        },
      }, modules);
    });
    setDomainExtensionIds(preset.required_extensions);
  }

  function toggleExtension(extension: Extension, enabled: boolean) {
    setProjectForm((current) => {
      const selected_extensions = enabled
        ? [...new Set([...current.selected_extensions, extension.id])]
        : current.selected_extensions.filter((id) => id !== extension.id);
      const modules = { ...current.modules };
      if (enabled) {
        for (const moduleId of extension.composed_module_ids) {
          const selectedModule = workspace.modules.find((item) => item.id === moduleId);
          if (selectedModule) modules[selectedModule.slot] = selectedModule.id;
        }
      } else {
        for (const moduleId of extension.composed_module_ids) {
          const selectedModule = workspace.modules.find((item) => item.id === moduleId);
          if (selectedModule && modules[selectedModule.slot] === selectedModule.id) delete modules[selectedModule.slot];
        }
      }
      const zonal = modules.balancing === "value-zonal-redispatch-balancing";
      return alignZonalSolverContract({
        ...current,
        selected_extensions,
        market_configuration: {
          ...current.market_configuration,
          zonal_demand_mode: zonal
            ? (current.market_configuration.zonal_demand_mode || "scenario_scaled_zonal_shares")
            : "",
        },
      }, modules);
    });
  }

  function chooseMethodology(profileId: string) {
    if (!methodologyCatalogue) return;
    const next = applyProfileChoice({ parameters: parameterValues, modules: projectForm.modules }, profileId, methodologyCatalogue);
    setParameterValues(next.parameters);
    setProjectForm((current) => ({ ...current, modules: next.modules }));
  }
  /** Spec 7: a method or data change of the saved Study opens the confirmation dialog; nothing runs until it is confirmed. */
  /** R4 M-低2: after the confirmation dialog closes, readiness is checked again for the Study as it now is. */
  async function recheckAfterMigration(projectId: string, saved: boolean) {
    const next = saved ? await refresh() : workspace;
    const project = next?.projects.find((item) => item.id === projectId);
    if (!project || project.id !== selectedProjectId || !effectivePreflightMode) return;
    // R5 低1, RR-1 (3): the answer to the user's choice ("Saved as a new
    // revision" or "The Study was not changed") survives the re-check.
    await checkPreflight(effectivePreflightMode, { project, askMigration: false, keepNotice: true });
  }
  async function promptMigration(project: Project, migration: RevisionMigration) {
    const opening = await openingMigration(API, project.id, migration);
    setMigrationPrompt({ projectId: project.id, studyName: project.name, migration: opening, nonce: Date.now() });
  }
  function selectStudyModule(slot: string, moduleId: string) {
    setProjectForm((current) => {
      const modules = { ...current.modules };
      if (moduleId) modules[slot] = moduleId; else delete modules[slot];
      if (slot === "psm") {
        const psm = workspace.modules.find((module) => module.id === moduleId);
        if (psm?.provides_capabilities?.includes("storage.central-cooptimization")) delete modules.storage_cost;
        else if (!modules.storage_cost) modules.storage_cost = "dynamic-annual-storage-cost";
      }
      const zonal = modules.balancing === "value-zonal-redispatch-balancing";
      return alignZonalSolverContract({
        ...current,
        market_configuration: {
          ...current.market_configuration,
          zonal_demand_mode: zonal
            ? (current.market_configuration.zonal_demand_mode || "scenario_scaled_zonal_shares")
            : "",
        },
      }, modules);
    });
  }

  /** The editable form of a saved Study: shared by Edit as new revision and the extension draft (R4 F-中4). */
  function loadStudyIntoForm(project: Project, name: string) {
    applyStudySnapshot(savedStudySnapshot(project, name));
  }
  /** Stop editing a saved Study.  The composer then gets a fresh new-Study form
   * (its unsaved edits stay stored under that Study's ID), so the loaded Study is
   * not mistaken for an unsaved new draft (W4a review). */
  function leaveStudyEdit() {
    if (editingProjectId) studyDraft.reset();
    setEditingBaseRevision(undefined); setEditingProjectId(undefined);
  }
  // R-15: Back from /studies/[id] to /studies leaves the edit the same way (URL effect).
  useEffect(() => { leaveStudyEditRef.current = leaveStudyEdit; });
  function loadProjectRevision(project: Project) {
    if (project.extensions?.frozen_recovery) { selectRunProject(project.id); setView("runCentre"); setNotice(t("studies.notice.frozenLocked")); return; }
    loadStudyIntoForm(project, project.name);
    setEditingBaseRevision(project.revision_sha256);
    setEditingProjectId(project.id);
    setPreflight(null);
    setSelectedProjectId(project.id);
    setSelectedRunId("");
    setNotice(t("studies.notice.loaded", { number: project.revision_number ?? 0 }));
  }

  function createFullReplayRevision() {
    const source = ["ready", "partial"].includes(selectedRunContext.kind) ? frozenRunProject : null;
    if (!source) {
      setNotice(t("workbench.frozenStudyUnavailable"));
      setView("run");
      return;
    }
    loadProjectRevision(source);
    setRuntimeValues((current) => ({ ...current, "runtime.market_trace_level": "full" }));
    setView("projects");
    setNotice(t("workbench.fullReplaySelected"));
  }

  async function createValue101BaselineStudy() {
    setLaunching("create-value-101-baseline");
    setNotice("");
    try {
      const response = await apiFetch(`${API}/tutorials/value-101/studies`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const payload = await response.json() as { error?: string; project?: Project; run_started?: boolean };
      if (!response.ok || !payload.project) throw new Error(payload.error || t("learn.notice.createFailed"));
      setSelectedProjectId(payload.project.id);
      setSelectedRunId("");
      await refresh();
      setNotice(payload.run_started === true ? t("learn.notice.createdAndStarted", { number: payload.project.revision_number ?? 1 }) : t("learn.notice.created", { number: payload.project.revision_number ?? 1 }));
    } catch (reason) {
      setNotice(reason instanceof Error ? reason.message : t("learn.notice.createFailed"));
    } finally {
      setLaunching("");
    }
  }

  async function moveStudyToTrash(project: Project, linkedRunCount: number) {
    const confirmation = buildStudyTrashConfirmation(project, linkedRunCount, t);
    const confirmed = confirmation.requiresExactName
      ? window.prompt(confirmation.message) === confirmation.expected
      : window.confirm(confirmation.message);
    if (!confirmed) { setNotice(t("studies.notice.trashCancelled")); return; }
    const reason = window.prompt(t("studies.notice.trashReason"), "") ?? "";
    setLaunching("trash-study"); setNotice("");
    try {
      const response = await apiFetch(`${API}/projects/${project.id}/trash`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true, confirm_name: confirmation.requiresExactName ? confirmation.expected : undefined, reason }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || t("studies.notice.trashFailed"));
      studyDraft.forget(project.id);
      if (editingProjectId === project.id) { leaveStudyEdit(); setPreflight(null); }
      if (selectedProjectId === project.id) {
        setSelectedProjectId(""); setSelectedRunId(""); setSelectedRunDetail(null); setPreflight(null);
      }
      await refresh();
      if (selectedProjectId === project.id) setSelectedProjectId("");
      setView("projects");
      setNotice(t("studies.notice.trashed", { name: project.name }));
    } catch (reasonValue) {
      setNotice(reasonValue instanceof Error ? reasonValue.message : t("studies.notice.trashFailed"));
    } finally { setLaunching(""); }
  }

  async function restoreStudyEntry(entry: StudyTrashEntry) {
    const previousSelection = selectedProjectId;
    setLaunching("restore-study"); setNotice("");
    try {
      const response = await apiFetch(`${API}/study-trash/${entry.trash_id}/restore`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || t("studies.notice.restoreFailed"));
      await refresh();
      setSelectedProjectId(previousSelection);
      setNotice(payload.needs_attention
        ? t("studies.notice.restoredAttention", { name: entry.study_name })
        : t("studies.notice.restored", { name: entry.study_name }));
    } catch (reasonValue) {
      setNotice(reasonValue instanceof Error ? reasonValue.message : t("studies.notice.restoreFailed"));
    } finally { setLaunching(""); }
  }

  function finishDataInstall() {
    dataInstallRequest.current = null;
    setDataInstalling(false);
    setDataInstallPhase("idle");
  }

  function cancelDataInstall() {
    if (dataInstallPhase !== "uploading") return;
    dataInstallRequest.current?.abort();
  }

  function installDataPack() {
    if (!dataBundle) { setNotice(t("data.install.needFile")); return; }
    if (!dataRights) { setNotice(t("data.install.needRights")); return; }
    setDataInstalling(true); setDataInstallProgress(0); setDataInstallPhase("uploading"); setNotice("");
    const request = new XMLHttpRequest();
    dataInstallRequest.current = request;
    request.open("POST", `${API}/data-packs/install`);
    request.setRequestHeader("Content-Type", "application/zip");
    request.setRequestHeader("X-Filename", encodeURIComponent(dataBundle.name));
    request.setRequestHeader("X-VALUE-Data-Rights", "acknowledged");
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percentage = Math.min(100, event.loaded / event.total * 100);
      setDataInstallProgress(percentage);
      if (percentage >= 100) setDataInstallPhase("verifying");
    };
    request.onload = () => {
      let payload: { error_code?: string; error?: string; installation?: { pack_id: string; name: string; validation: { passed: number } } } = {};
      try { payload = JSON.parse(request.responseText); } catch { /* The status remains the authoritative failure. */ }
      if (request.status < 200 || request.status >= 300 || !payload.installation) {
        setNotice(`${errorPrefix(t, payload.error_code)}${payload.error || t("data.install.failed", { status: request.status })}`);
        finishDataInstall();
        return;
      }
      setSelectedPackId(payload.installation.pack_id);
      setNotice(t("data.install.installed", { name: payload.installation.name, count: payload.installation.validation.passed }));
      setDataBundle(null); setDataRights(false); setDataInstallProgress(100);
      void refresh().finally(finishDataInstall);
    };
    request.onerror = () => { setNotice(t("data.install.unreachable")); finishDataInstall(); };
    request.onabort = () => { setNotice(t("data.install.cancelled")); finishDataInstall(); };
    request.send(dataBundle);
  }

  function finishResearchSuiteInstall() {
    researchSuiteInstallRequest.current = null;
    setResearchSuiteInstalling(false);
    setResearchSuiteInstallPhase("idle");
  }

  function cancelResearchSuiteInstall() {
    if (researchSuiteInstallPhase !== "uploading") return;
    researchSuiteInstallRequest.current?.abort();
  }

  function installResearchSuite() {
    if (!researchSuiteBundle) { setNotice(t("data.suite.needFile")); return; }
    if (!researchSuiteRights) { setNotice(t("data.suite.needRights")); return; }
    setResearchSuiteInstalling(true); setResearchSuiteInstallProgress(0); setResearchSuiteInstallPhase("uploading"); setResearchSuiteSummary(null); setNotice("");
    const request = new XMLHttpRequest();
    researchSuiteInstallRequest.current = request;
    request.open("POST", researchSuiteApiUrl());
    request.setRequestHeader("Content-Type", "application/zip");
    request.setRequestHeader("X-Filename", encodeURIComponent(researchSuiteBundle.name));
    request.setRequestHeader("X-VALUE-Data-Rights", "acknowledged");
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      const percentage = Math.min(100, event.loaded / event.total * 100);
      setResearchSuiteInstallProgress(percentage);
      if (percentage >= 100) setResearchSuiteInstallPhase("verifying");
    };
    request.onload = async () => {
      let payload: { error_code?: string; error?: string; installation?: ResearchSuiteInstallation } = {};
      try { payload = JSON.parse(request.responseText); } catch { /* HTTP status remains authoritative. */ }
      if (request.status < 200 || request.status >= 300 || !payload.installation) {
        setNotice(`${errorPrefix(t, payload.error_code)}${payload.error || t("data.suite.failed", { status: request.status })}`);
        finishResearchSuiteInstall();
        return;
      }
      const summary = describeResearchSuiteInstallation(payload.installation) as ResearchSuiteSummary;
      setResearchSuiteSummary(summary);
      setResearchSuiteBundle(null); setResearchSuiteRights(false); setResearchSuiteInstallProgress(100);
      await refresh();
      setSelectedPackId(summary.components[0]?.id ?? selectedPackId);
      setNotice(t(summary.idempotent ? "data.suite.verified" : "data.suite.installed", { suite: summary.suiteId }));
      finishResearchSuiteInstall();
    };
    request.onerror = () => { setNotice(t("data.suite.unreachable")); finishResearchSuiteInstall(); };
    request.onabort = () => { setNotice(t("data.suite.cancelled")); finishResearchSuiteInstall(); };
    request.send(researchSuiteBundle);
  }

  function openResearchSuiteStudy(studyId: string) {
    setSelectedProjectId(studyId);
    setSelectedRunId("");
    leaveStudyEdit();
    setPreflight(null);
    setView("projects");
  }

  /** POST a module/extension lifecycle change; when Runs are pending (P0-2, 409
   * GF_MODULE_LIFECYCLE_RUNS_PENDING) ask, then resend with the confirmation. */
  async function lifecycleRequest(url: string, init: RequestInit, jsonBody?: Record<string, unknown>): Promise<{ response: Response; payload: Record<string, unknown> & { error?: string; error_code?: string } }> {
    const send = async (confirmed: boolean) => {
      const headers = new Headers(init.headers);
      let body = init.body;
      if (confirmed) {
        if (jsonBody !== undefined) body = JSON.stringify({ ...jsonBody, confirm_pending_runs: true });
        else headers.set("X-VALUE-Confirm-Pending-Runs", "acknowledged");
      }
      const response = await apiFetch(url, { ...init, headers, body });
      let payload: Record<string, unknown> & { error?: string; error_code?: string } = {};
      try { payload = await response.json(); } catch { /* the status is authoritative */ }
      return { response, payload };
    };
    const first = await send(false);
    if (!isPendingRunsRefusal(first.response.status, first.payload.error_code)) return first;
    if (!window.confirm(pendingRunsQuestion(first.payload.error, url.includes("/extensions/") ? "extensions" : "modules", t))) return first;
    return send(true);
  }

  const [quarantineBusy, setQuarantineBusy] = useState("");
  // Spec 11.4 (M-D4): the error of the last Enable attempt per entry; a Rescan clears them.
  const [entryErrors, setEntryErrors] = useState<Record<string, EntryError>>({});
  async function disableQuarantined(row: QuarantineRow) {
    if (!row.disablePath) return;
    setQuarantineBusy(row.key); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}${row.disablePath.replace(/^\/api/, "")}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, {});
      if (!response.ok) throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error || t("modules.notice.disableFailed", { id: row.id ?? row.label })}`);
      const parkedCopies = (payload as { installation?: { parked_manifests?: string[] } }).installation?.parked_manifests ?? [];
      setNotice(`${t("modules.notice.quarantineDisabled", { id: row.id ?? row.label })}${parkedCopies.length ? ` ${t("modules.notice.parkedManifests", { count: parkedCopies.length, files: parkedCopies.map((file) => `modules/${file}`).join(", ") })}` : ""}${stoppedRunsNotice(payload, t)}`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("modules.notice.disableFailed", { id: row.id ?? row.label })); }
    finally { setQuarantineBusy(""); }
  }
  async function rescanModules() {
    setQuarantineBusy("rescan"); setNotice("");
    try {
      const response = await apiFetch(`${API}/modules/rescan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json() as { status?: string; error?: string; error_code?: string };
      if (!response.ok) throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error || t("modules.notice.rescanFailed")}`);
      setNotice(payload.status === "ok" ? t("modules.notice.rescanClean") : t("modules.notice.rescanQuarantined")); setEntryErrors({}); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("modules.notice.rescanFailed")); }
    finally { setQuarantineBusy(""); }
  }

  function recordEntryError(key: string, error: EntryError | null) {
    setEntryErrors((current) => error ? { ...current, [key]: error } : Object.fromEntries(Object.entries(current).filter(([item]) => item !== key)));
  }
  /** Spec 11.4: Enable from the Disabled and quarantined area; a failure stays on its row with Rescan. */
  async function enableEntry(entry: DisabledEntry) {
    setQuarantineBusy(`enable:${entry.key}`); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}${lifecyclePath(entry, "enable")}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, {});
      if (!response.ok) throw new EntryLifecycleError(payload.error || t("modules.notice.enableFailed", { id: entry.id }), payload.error_code);
      recordEntryError(entry.key, null);
      setNotice(`${t("modules.notice.enabled", { id: entry.id })}${stoppedRunsNotice(payload, t)}`); setPreflight(null); await refresh();
    } catch (reason) { recordEntryError(entry.key, { code: reason instanceof EntryLifecycleError ? reason.code : undefined, message: reason instanceof Error ? reason.message : t("modules.notice.enableFailed", { id: entry.id }) }); }
    finally { setQuarantineBusy(""); }
  }
  /** Spec 11.4: Remove (confirmed in the panel) moves the entry's files out of the scanned folders. */
  async function removeEntry(entry: DisabledEntry) {
    setQuarantineBusy(`remove:${entry.key}`); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}${lifecyclePath(entry, "remove")}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" }, {}) as { response: Response; payload: { error?: string; error_code?: string; dependents?: Record<string, string[]>; removed?: { destination?: string } } };
      if (!response.ok) {
        const dependents = Object.values(payload.dependents ?? {}).flat();
        throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error || t("modules.notice.removeFailed", { id: entry.id })}${dependents.length ? ` — ${dependents.join(", ")}` : ""}`);
      }
      recordEntryError(entry.key, null);
      setNotice(`${t("modules.notice.removed", { id: entry.id, destination: payload.removed?.destination ?? "disabled-manifests/removed" })}${stoppedRunsNotice(payload, t)}`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("modules.notice.removeFailed", { id: entry.id })); }
    finally { setQuarantineBusy(""); }
  }

  async function installModule() {
    if (!moduleBundle) { setNotice(t("modules.installer.needFile")); return; }
    if (!moduleTrust) { setNotice(t("modules.installer.needTrust")); return; }
    setModuleInstalling(true); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/modules/install`, {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Filename": encodeURIComponent(moduleBundle.name),
          "X-VALUE-Executable-Trust": "acknowledged",
        },
        body: moduleBundle,
      }) as { response: Response; payload: { error?: string; error_code?: string; installation: { name: string; module_version: string } } };
      if (!response.ok) throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error || t("modules.notice.moduleInstallFailed")}`);
      setNotice(`${t("modules.notice.moduleInstalled", { name: payload.installation.name, version: payload.installation.module_version })}${stoppedRunsNotice(payload, t)}`);
      setModuleBundle(null); setModuleTrust(false); setBundleInputGeneration((generation) => generation + 1); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("modules.notice.moduleInstallFailed")); }
    finally { setModuleInstalling(false); }
  }

  async function changeModuleState(installation: ModuleInstallation, enabled: boolean) {
    setModuleLifecycle(installation.module_id); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/modules/${encodeURIComponent(installation.module_id)}/${enabled ? "enable" : "disable"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      }, {}) as { response: Response; payload: { error?: string; error_code?: string; dependents?: { projects?: string[] } } };
      if (!response.ok) {
        const projects = payload.dependents?.projects?.join(", ");
        throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error}${projects ? `: ${projects}` : ""}`);
      }
      setNotice(`${t(enabled ? "modules.notice.moduleEnabled" : "modules.notice.moduleDisabled", { name: installation.name })}${stoppedRunsNotice(payload, t)}`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("modules.notice.moduleStateFailed")); }
    finally { setModuleLifecycle(""); }
  }

  async function installExtension() {
    if (!extensionBundle) { setNotice(t("extensions.installer.needFile")); return; }
    if (!extensionTrust) { setNotice(t("extensions.installer.needTrust")); return; }
    setExtensionInstalling(true); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/extensions/install`, {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-Filename": encodeURIComponent(extensionBundle.name),
          "X-VALUE-Executable-Trust": "acknowledged",
        },
        body: extensionBundle,
      }) as { response: Response; payload: { error?: string; error_code?: string; installation: { extension_id: string; version: string } } };
      if (!response.ok) throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error || t("extensions.notice.installFailed")}`);
      setNotice(`${t("extensions.notice.installed", { id: payload.installation.extension_id, version: payload.installation.version })}${stoppedRunsNotice(payload, t)}`);
      setExtensionBundle(null); setExtensionTrust(false); setBundleInputGeneration((generation) => generation + 1); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("extensions.notice.installFailed")); }
    finally { setExtensionInstalling(false); }
  }

  async function changeExtensionState(installation: ExtensionInstallation, enabled: boolean) {
    setExtensionLifecycle(installation.extension_id); setNotice("");
    try {
      const { response, payload } = await lifecycleRequest(`${API}/extensions/${encodeURIComponent(installation.extension_id)}/${enabled ? "enable" : "disable"}`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      }, {}) as { response: Response; payload: { error?: string; error_code?: string; dependents?: { projects?: string[]; runs_and_retained_history?: string[] } } };
      if (!response.ok) {
        const dependents = [...(payload.dependents?.projects ?? []), ...(payload.dependents?.runs_and_retained_history ?? [])];
        throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error}${dependents.length ? ` — ${dependents.join(", ")}` : ""}`);
      }
      setNotice(`${t(enabled ? "extensions.notice.enabled" : "extensions.notice.disabled", { id: installation.extension_id })}${stoppedRunsNotice(payload, t)}`); setPreflight(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("extensions.notice.stateFailed")); }
    finally { setExtensionLifecycle(""); }
  }

  async function copyDraftDataPack() {
    const source = dataContextPack;
    if (!source?.manifest_sha256 || copyingDraftPack || !draftPackCopyName.trim() || source.data_pack_type === "network_overlay") return;
    setCopyingDraftPack(true); setNotice("");
    try {
      const response = await apiFetch(`${API}/data-packs/${encodeURIComponent(source.id)}/clone`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schema_version: "value.data-pack-clone-request/v1", name: draftPackCopyName.trim(), source_manifest_sha256: source.manifest_sha256 }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.data_pack?.id || payload.data_pack.id === source.id) throw new Error(payload.error || t("data.notice.copyRefused"));
      await refresh();
      setSelectedPackId(payload.data_pack.id); setDataContextId("draft");
      setDraftResolution(null); setPreflight(null); setSavedDataResolution(null); setDataPreview(null);
      setDraftPackCopyName("");
      setNotice(t("data.notice.copied"));
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("data.notice.copyFailed")); }
    finally { setCopyingDraftPack(false); }
  }

  async function upload(role: string, file?: File) {
    if (!file || !dataContextPack || uploading) return;
    if (isJourneyData && (journeyReadOnlyReason || !dataContextResolution || (journeyNetworkPackId && role.startsWith("value.zonal.")))) {
      setNotice(journeyReadOnlyReason || t("data.notice.waitForContract")); return;
    }
    if (workspace.projects.some((project) => project.data_pack_id === dataContextPack.id)) {
      setNotice(t("data.role.uploadLocked")); return;
    }
    const target = dataContextPack;
    ++dataPreviewRequest.current; setDataPreview(null); setDataPreviewLoading("");
    setUploading(role); setNotice(""); setPreflight(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/octet-stream", "X-Filename": encodeURIComponent(file.name) };
      if (target.manifest_sha256) headers["X-Expected-Pack-Revision"] = target.manifest_sha256;
      const response = await apiFetch(`${API}/data-packs/${encodeURIComponent(target.id)}/files/${encodeURIComponent(role)}`, { method: "POST", headers, body: file });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || t("data.notice.importFailed"));
      setNotice(t("data.notice.imported", { file: file.name, pack: target.name }));
      setSavedDataResolution(null); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("data.notice.importFailed")); }
    finally { setUploading(""); }
  }
  async function previewParameters() {
    if (!selectedPack) return;
    try {
      const response = await apiFetch(`${API}/parameters/preview`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ data_pack_id: selectedPack.id, parameters: parameterValues, runtime_options: runtimeValues }) });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || t("studies.notice.parametersFailed"));
      setResolvedSources(payload.sources ?? {}); setNotice(t("studies.notice.parametersChecked"));
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("studies.notice.parametersFailed")); }
  }
  /** F4-03 (P1 spec 6.2): one request at a time (a double click sends one POST); a
   * refusal or an unreachable service is reported and the draft is kept. */
  async function saveProject() {
    if (!selectedPack || savingStudyRef.current) return;
    if (draftResolving || !draftResolution?.valid) { setNotice(t("studies.save.resolveFirst")); return; }
    savingStudyRef.current = true; setSavingStudy(true);
    const draftKeyId = editingProjectId;
    const taken = [...workspace.projects, ...workspace.study_trash.map((entry) => ({ id: entry.study_id }))];
    try {
      let response: Response;
      try {
        response = await apiFetch(`${API}/projects`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...projectForm, id: editingProjectId, extension_parameters: { ...draftResolution.effective_extension_parameters, ...projectForm.extension_parameters }, data_pack_id: selectedPack.id, parameters: parameterValues, runtime_options: runtimeValues, base_revision_sha256: editingBaseRevision }) });
      } catch {
        setNotice(saveFailureNotice({ kind: "network" }, t, projectForm.name, taken)); return;
      }
      const payload = await response.json().catch(() => ({})) as { error?: string; error_code?: string; study_id?: string; project?: Project; validation?: { errors?: string[]; resolved_parameters?: { sources?: Record<string, { source?: string }> } } };
      if (!response.ok || !payload.project) {
        const failure: SaveFailure = { kind: "refused", status: response.status, code: payload.error_code, error: payload.error, studyId: payload.study_id };
        setNotice(saveFailureNotice(failure, t, projectForm.name, taken)); return;
      }
      studyDraft.forget(draftKeyId);
      // The composer holds the saved, normalised revision: it is its own baseline, so not "unsaved".
      applyStudySnapshot(savedStudySnapshot(payload.project));
      setResolvedSources(payload.validation?.resolved_parameters?.sources ?? {}); setSelectedProjectId(payload.project.id); setSelectedRunId(""); setEditingBaseRevision(payload.project.revision_sha256); setEditingProjectId(payload.project.id); setPreflight(null); setNotice(payload.validation?.errors?.[0] || t("studies.save.saved")); await refresh(); setView("runCentre");
    } finally {
      savingStudyRef.current = false; setSavingStudy(false);
    }
  }
  async function onRecoveredStudyCreated(projectId: string, mode: string) {
    const next = await refresh();
    if (!next?.projects.some(project => project.id === projectId)) throw new Error(t("workbench.createdStudyMissing"));
    if (!ALL_RUN_MODES.includes(mode as RunMode)) throw new Error(t("workbench.scopeUnsupported"));
    preflightRequest.current += 1; setPendingPreflightKey(null);
    setSelectedProjectId(projectId); setSelectedRunId(""); setSelectedRunDetail(null);
    setPreflight(null); setPreflightMode(mode as RunMode); setView("runCentre");
    setNotice(t("workbench.recoveredStudySaved"));
  }
  async function checkPreflight(mode = effectivePreflightMode, options: { project?: Project; askMigration?: boolean; keepNotice?: boolean } = {}) {
    if (!mode || !canRunMode(mode)) { setNotice(t("workbench.scopeIncompatible")); return; }
    const target = options.project ?? selectedProject;
    if (!target) { setNotice(t("workbench.saveStudyFirst")); return; }
    const requestId = ++preflightRequest.current;
    setPendingPreflightKey(preflightKey(target, mode)); setPreflight(null); if (!options.keepNotice) setNotice("");
    try {
      const response = await apiFetch(`${API}/projects/${encodeURIComponent(target.id)}/preflight`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
      const payload = await response.json();
      if (requestId !== preflightRequest.current) return;
      if (!response.ok) throw new Error(payload.error || t("workbench.preflightFailed"));
      // Spec 7: a method or data change is reported against the declared revision; it opens the confirmation dialog.
      // R4 M-低2: not while the installation itself blocks every Run (fix that first), and not
      // when readiness is re-checked after the user cancelled the confirmation.
      const migration = migrationFromResponse(payload);
      const environment = environmentBlockers(payload);
      if (migration && !environment.length && options.askMigration !== false && payload.project_id === target.id && migration.declared_sha256 === target.revision_sha256) {
        setNotice(t("workbench.migrationNeeded"));
        void promptMigration(target, migration);
        return;
      }
      if (!preflightMatches(payload, target, mode)) throw new Error(t("workbench.preflightIdentityChanged"));
      // Rendering also matches the current selection, so an old Study response cannot appear on a new one.
      setPreflight(payload);
      if (migration && environment.length) setNotice(t("workbench.fixInstallationFirst"));
    } catch (reason) { if (requestId === preflightRequest.current) setNotice(reason instanceof Error ? reason.message : t("workbench.preflightFailed")); }
    finally { if (requestId === preflightRequest.current) setPendingPreflightKey(null); }
  }
  async function startRun(mode: RunMode, projectOverride?: Project) {
    const targetProject = projectOverride ?? selectedProject;
    const targetPack = workspace.data_packs.find(pack => pack.id === targetProject?.data_pack_id);
    if (!runModesForStudy(targetProject, targetPack).includes(mode)) { setNotice(t("workbench.scopeOutside")); return; }
    if (!targetProject) { setNotice(t("workbench.saveStudyFirst")); setView("projects"); return; }
    setSelectedProjectId(targetProject.id);
    setLaunching(mode); setNotice(""); setStartedRun(null);
    const launchView = viewRef.current;
    try {
      const response = await apiFetch(`${API}/projects/${targetProject.id}/runs`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode }) });
      const payload = await response.json(); if (!response.ok) { if (preflightMatches(payload.preflight, targetProject, mode)) { setPreflight(payload.preflight); } const migration = migrationFromResponse(payload); if (migration && migration.declared_sha256 === targetProject.revision_sha256) void promptMigration(targetProject, migration); throw new Error(payload.error || t("workbench.startFailed")); }
      // W4c: a Run started from the Run centre stays there, selected, with its progress.
      const noticeView = viewRef.current === launchView ? "runCentre" : viewRef.current;
      if (viewRef.current === launchView) { setSelectedRunId(payload.run.id); setView("runCentre"); }
      setStartedRun({ runId: payload.run.id, mode, studyId: targetProject.id, view: noticeView, text: t(mode === "smoke" ? "workbench.started.smoke" : mode === "two_year_smoke" ? "workbench.started.twoYearSmoke" : mode === "value_101_day" ? "workbench.started.lesson" : mode === "two_year" ? "workbench.started.twoYear" : "workbench.started.full") });
      await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("workbench.launchFailed")); } finally { setLaunching(""); }
  }
  async function resumeRun(run: ModelRun) {
    setLaunching("resume"); setNotice("");
    try {
      const response = await apiFetch(`${API}/runs/${run.id}/resume`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || t("workbench.resumeUnable"));
      setNotice(t("workbench.resuming")); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("workbench.resumeFailed")); }
    finally { setLaunching(""); }
  }
  async function markRunLost(run: ModelRun) {
    // Spec 5 / P0-3 S4: a second, explicit confirmation in which the user types the exact run ID (as Delete does); only that ID is sent to the API's confirmation gate.
    const confirmation = window.prompt(t("workbench.markLost.prompt", { runId: run.id }));
    if (confirmation !== run.id) { setNotice(t("workbench.markLost.cancelled")); return; }
    setLaunching("mark-lost"); setNotice("");
    try {
      const response = await apiFetch(`${API}/runs/${encodeURIComponent(run.id)}/mark-lost`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm_run_id: confirmation }) });
      const payload = await response.json() as { error?: string; error_code?: string };
      if (!response.ok) throw new Error(`${errorPrefix(t, payload.error_code)}${payload.error || t("runStatus.markLostFailed")}`);
      setNotice(t("workbench.markLost.done")); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("workbench.markLost.failed")); }
    finally { setLaunching(""); }
  }
  /** R6-1 (EM-中1): a Run stopped before it started because the installed code
   * changed is resubmitted as a new Run of the same Study and scope. */
  async function resubmitRun(run: ModelRun) {
    const project = workspace.projects.find((item) => item.id === run.project_id);
    if (!project) { setNotice(t("workbench.resubmitNoStudy")); return; }
    await startRun(run.mode as RunMode, project);
  }
  async function rerunAsCopperplate(run: ModelRun) {
    setLaunching("rerun-copperplate"); setNotice("");
    try {
      const response = await apiFetch(`${API}/runs/${run.id}/rerun-copperplate`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || t("workbench.copperplate.unable"));
      setSelectedRunId(payload.run.id);
      setNotice(t("workbench.copperplate.created", { runId: payload.run.id }));
      await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("workbench.copperplate.failed")); }
    finally { setLaunching(""); }
  }
  async function cloneStoragePolicy(moduleId: string, projectOverride?: Project) {
    const targetProject = projectOverride ?? selectedProject;
    if (!targetProject) return;
    setLaunching(`clone-${moduleId}`); setNotice("");
    try {
      const response = await apiFetch(`${API}/projects/${targetProject.id}/clone-storage-policy`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ storage_cost_module_id: moduleId }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || t("workbench.clone.unable"));
      await refresh();
      loadProjectRevision(payload.project as Project);
      setView("projects");
      setNotice(t("workbench.clone.created", { moduleId }));
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("workbench.clone.failed")); }
    finally { setLaunching(""); }
  }
  async function lifecycleAction(run: ModelRun, action: "cancel" | "archive" | "restore" | "export" | "delete") {
    setLaunching(action); setNotice("");
    try {
      let body: Record<string, string> = action === "export" ? { profile: "complete_audit" } : {};
      if (action === "delete") {
        // F4-06 (spec 6.5): VALUE moves the Run folder to its local trash folder and has no restore for Runs; say so.
        const confirmation = window.prompt(t("runs.delete.prompt", { runId: run.id }));
        if (confirmation !== run.id) { setNotice(t("runs.delete.cancelled")); return; }
        body = { confirm_run_id: run.id };
      }
      const response = await apiFetch(`${API}/runs/${run.id}/${action}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const payload = await response.json(); if (!response.ok) throw new Error(payload.error || t("workbench.action.failed", { action }));
      setNotice(action === "cancel" ? t("workbench.action.cancelled") : action === "export" ? t("workbench.action.exported") : action === "delete" ? (typeof payload.moved_to === "string" && payload.moved_to ? t("runs.delete.done", { path: payload.moved_to }) : t("runs.delete.doneNoPath")) : t("workbench.action.completed", { action })); await refresh();
    } catch (reason) { setNotice(reason instanceof Error ? reason.message : t("workbench.action.failed", { action })); }
    finally { setLaunching(""); }
  }
  return {
    routedView,
    view,
    setView,
    activePath,
    setActivePath,
    readMeOpen,
    setReadMeOpen,
    t,
    store,
    workspace,
    definitions,
    setDefinitions,
    online,
    launcherRequired,
    refreshFailures,
    workspaceLoaded,
    health,
    connectionState,
    selectedPackId,
    setSelectedPackId,
    selectedProjectId,
    setSelectedProjectId,
    selectedRunId,
    setSelectedRunId,
    selectedRunDetail,
    setSelectedRunDetail,
    uploading,
    setUploading,
    dataBundle,
    setDataBundle,
    dataRights,
    setDataRights,
    dataInstalling,
    setDataInstalling,
    dataInstallProgress,
    setDataInstallProgress,
    dataInstallPhase,
    setDataInstallPhase,
    researchSuiteBundle,
    setResearchSuiteBundle,
    researchSuiteRights,
    setResearchSuiteRights,
    researchSuiteInstalling,
    setResearchSuiteInstalling,
    researchSuiteInstallProgress,
    setResearchSuiteInstallProgress,
    researchSuiteInstallPhase,
    setResearchSuiteInstallPhase,
    researchSuiteSummary,
    setResearchSuiteSummary,
    moduleBundle,
    setModuleBundle,
    bundleInputGeneration,
    setBundleInputGeneration,
    moduleTrust,
    setModuleTrust,
    moduleInstalling,
    setModuleInstalling,
    moduleLifecycle,
    setModuleLifecycle,
    extensionBundle,
    setExtensionBundle,
    extensionTrust,
    setExtensionTrust,
    extensionInstalling,
    setExtensionInstalling,
    extensionLifecycle,
    setExtensionLifecycle,
    launching,
    setLaunching,
    replayTarget,
    setReplayTarget,
    stressEventsFocus,
    setStressEventsFocus,
    inspectTarget,
    setInspectTarget,
    openView,
    methodologyCatalogue,
    setMethodologyCatalogue,
    methodologyError,
    setMethodologyError,
    migrationPrompt,
    setMigrationPrompt,
    preflightMode,
    setPreflightMode,
    storedPreflight,
    setPreflight,
    pendingPreflightKey,
    setPendingPreflightKey,
    notice,
    setNotice,
    startedRun,
    setStartedRun,
    parameterValues,
    setParameterValues,
    runtimeValues,
    setRuntimeValues,
    resolvedSources,
    setResolvedSources,
    draftResolution,
    setDraftResolution,
    draftResolving,
    draftResolutionError,
    savingStudy,
    studyDraft,
    resetStudyDraft: studyDraft.reset,
    leaveStudyEdit,
    composerInitialStep,
    setComposerInitialStep,
    draftPackCopyName,
    setDraftPackCopyName,
    copyingDraftPack,
    setCopyingDraftPack,
    dataContextId,
    setDataContextId,
    journeyTargetPackId,
    setJourneyTargetPackId,
    journeyData,
    setJourneyData,
    savedDataResolution,
    setSavedDataResolution,
    dataPreviewResult,
    setDataPreview,
    dataPreviewLoading,
    setDataPreviewLoading,
    domainExtensionIds,
    setDomainExtensionIds,
    editingBaseRevision,
    setEditingBaseRevision,
    editingProjectId,
    setEditingProjectId,
    frozenRunReadiness,
    setFrozenRunReadiness,
    frozenRunProject,
    setFrozenRunProject,
    frozenInputSnapshot,
    setFrozenInputSnapshot,
    frozenRunSelectionId,
    setFrozenRunSelectionId,
    value101Tutorial,
    setValue101Tutorial,
    value101Loading,
    setValue101Loading,
    value101Error,
    setValue101Error,
    projectForm,
    setProjectForm,
    refresh,
    refreshValue101Tutorial,
    projectRuns,
    selectedRunSummary,
    frozenRunId,
    frozenSnapshotWritten,
    hasActiveRun,
    activeRunCount,
    selectedPack,
    selectedProject,
    selectedProjectPack,
    allowedStudyModes,
    canRunMode,
    effectivePreflightMode,
    currentPreflightKey,
    checkingPreflight,
    preflight,
    selectRunProject,
    zonalPreflight,
    selectedRun,
    selectedRunSourceMutable,
    isRunView,
    selectedRunContext,
    locationRunId,
    locationRunStudyId,
    chooseCommunityPath,
    value101Project,
    value101Trash,
    value101DayRun,
    value101AnnualRun,
    value101Preparations,
    teachingProject,
    readyModules,
    experimentalModules,
    draftPackManifest,
    journeySource,
    journeySourceCurrent,
    journeySourcePack,
    isJourneyData,
    dataContextProject,
    dataContextPackId,
    dataContextPack,
    dataManifestSha256,
    journeyNetworkPackId,
    journeyReadOnlyReason,
    dataContextKey,
    dataContextResolution,
    activeDataSlots,
    dataGroups,
    dataContextExtensions,
    dataPreview,
    packValidationResult,
    setPackValidationResult,
    packValidationNonce,
    setPackValidationNonce,
    packValidationPackId,
    packValidationExtensions,
    packValidationKey,
    packValidationCurrent,
    packValidationLayers,
    previewDataRole,
    chooseDomain,
    toggleExtension,
    chooseMethodology,
    recheckAfterMigration,
    promptMigration,
    selectStudyModule,
    loadStudyIntoForm,
    loadProjectRevision,
    createFullReplayRevision,
    createValue101BaselineStudy,
    moveStudyToTrash,
    restoreStudyEntry,
    finishDataInstall,
    cancelDataInstall,
    installDataPack,
    finishResearchSuiteInstall,
    cancelResearchSuiteInstall,
    installResearchSuite,
    openResearchSuiteStudy,
    lifecycleRequest,
    quarantineBusy,
    setQuarantineBusy,
    entryErrors,
    setEntryErrors,
    disableQuarantined,
    rescanModules,
    recordEntryError,
    enableEntry,
    removeEntry,
    installModule,
    changeModuleState,
    installExtension,
    changeExtensionState,
    copyDraftDataPack,
    upload,
    previewParameters,
    saveProject,
    onRecoveredStudyCreated,
    checkPreflight,
    startRun,
    resumeRun,
    markRunLost,
    resubmitRun,
    rerunAsCopperplate,
    cloneStoragePolicy,
    lifecycleAction,
  };
}

export type WorkbenchState = ReturnType<typeof useWorkbenchState>;
