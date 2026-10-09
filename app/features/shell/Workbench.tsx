"use client";

// The application shell (P1 spec 5.2, W3).  Mounted once by the root layout:
// it holds the workbench state (useWorkbenchState), so a Study draft, a
// selection or a running upload survives a route change, and renders what
// every page shares - skip link, top bar, sidebar, Run context, notices and the
// migration dialog - around the route's page (children).
//
// Landmarks in order: header (top bar), nav (sidebar), main (page; the sidebar
// is outside it, F2-04).
import { createContext, useContext, useEffect, useRef, type ReactNode } from "react";
import { API_BASE, contractStatus } from "../../lib/api.ts";
import { WorkspaceStoreProvider } from "../../lib/workspaceStore.ts";
import { Badge, modelDisplayName } from "../shared/presentation";
import OpenFromLauncher from "../shared/OpenFromLauncher";
import { findNavView, navGroupLabel, type View } from "../shared/navigation.ts";
import { baseInputsPill } from "../shared/headerPill.ts";
import StudyMigrationDialog from "../studies/StudyMigrationDialog";
import ReadMePanel from "../workspace/ReadMePanel";
import RunContextBar from "../workspace/RunContextBar";
import { startedRunNoticeText, startedRunNoticeVisible } from "../runs/runHistoryView.ts";
import ContractMismatch from "./ContractMismatch";
import RunSectionNav from "./RunSectionNav";
import WorkspaceRail from "./WorkspaceRail";
import { useNarrowViewport } from "./useNarrowViewport.ts";
import { isRunSectionView, routePathname } from "./routes.ts";
import { useWorkbenchState, type WorkbenchState } from "./useWorkbenchState.ts";
import "../shared/service-status.css";
import "../workspace/workspace-shell.css";
import "../shared/narrow-layout.css";
import "../market/market-replay.css";
// Styles shared by several pages are loaded with the shell: a style file
// imported by two route chunks alone becomes a style-only chunk whose empty
// script vinext still lists for preloading (a 404 on Learn and Runs).
import "../runs/run-history.css";
import "./shell.css";

const WorkbenchContext = createContext<WorkbenchState | null>(null);

/** The workbench state for a route's page. */
export function useWorkbench(): WorkbenchState {
  const value = useContext(WorkbenchContext);
  if (!value) throw new Error("useWorkbench() is only available inside the workbench shell (app/layout.tsx).");
  return value;
}

export default function Workbench({ children }: { children: ReactNode }) {
  const workbench = useWorkbenchState();
  const {
    t, view, routedView, openView, setView, store, workspace, online, launcherRequired, health, connectionState, refreshFailures, refresh,
    selectedPack, setSelectedPackId, selectedProject, selectedProjectPack, selectedProjectId, selectedRunId, selectedRun, selectedRunSummary,
    isRunView, isJourneyData, dataContextId, editingProjectId, projectForm, activeRunCount,
    readMeOpen, setReadMeOpen, frozenRunSelectionId, frozenRunProject, frozenInputSnapshot, setInspectTarget, setReplayTarget, setStressEventsFocus,
    notice, setNotice, startedRun, setStartedRun, migrationPrompt, setMigrationPrompt, setPreflight, recheckAfterMigration,
  } = workbench;
  const runId = selectedRunId || selectedRunSummary?.id || "";

  // Spec 5.2: after a route change, focus moves to the page title so a screen
  // reader announces the new page; the first render leaves focus alone.
  const heading = useRef<HTMLHeadingElement>(null);
  const narrow = useNarrowViewport();
  const shownView = useRef<View>(routedView);
  useEffect(() => {
    if (shownView.current !== routedView) heading.current?.focus({ preventScroll: true });
    shownView.current = routedView;
  }, [routedView]);

  if (launcherRequired) return <OpenFromLauncher />;
  // P1 spec 4: an interface and a local service built for different contracts must not talk.
  if (contractStatus(health) === "mismatch") return <ContractMismatch serviceContract={health?.frontend_contract_version} />;
  const currentView = findNavView(view);
  // R3-04: next to a selected saved Study the header names that Study's data
  // pack; the draft data pack (for a new Study) is chosen only where a draft is
  // edited (Studies, or Data for the draft) or while no saved Study is selected.
  const draftContext = view === "projects" || (view === "data" && dataContextId === "draft") || !selectedProject;
  const headerPack = draftContext ? selectedPack : selectedProjectPack;
  const pill = baseInputsPill(online, headerPack, t);
  const showPack = !isRunView && view !== "journey" && !(view === "data" && isJourneyData);
  // Spec 5.2: the Run context bar belongs to the pages of one Run
  // (/runs/[runId]/*); Inspect reads one Run's ledgers and keeps it (D-W3-3).
  const runRoute = (isRunSectionView(view) && Boolean(runId)) || view === "audit";
  const service = { state: connectionState, failures: refreshFailures, health, runtime: workspace.runtime, architectureVersion: workspace.architecture_version };
  const packMeta = showPack ? (draftContext
    ? <><label><span>{t("header.draftPack")}</span><select aria-label={t("header.draftPackSelect")} value={selectedPack?.id ?? ""} onChange={(event) => setSelectedPackId(event.target.value)} disabled={!online}>{workspace.data_packs.map((pack) => <option value={pack.id} key={pack.id}>{modelDisplayName(pack.name)}</option>)}</select></label><span title={t("header.baseInputsTitle")}>{/* F2-N3 (round R1-5): this count is the pack's base roles only. */}<Badge tone={pill.tone}>{pill.text}</Badge></span></>
    : <><span className="top-meta-pack" title={t("header.studyPackTitle")}><span>{t("header.studyPack")}</span><b>{selectedProjectPack ? modelDisplayName(selectedProjectPack.name) : selectedProject?.data_pack_id}</b></span><span title={t("header.baseInputsTitle")}><Badge tone={pill.tone}>{pill.text}</Badge></span></>) : null;
  const backgroundRuns = activeRunCount > 0 ? <button type="button" className="background-runs value-new-control" onClick={() => setView("runCentre")}>{t("header.backgroundRuns", { count: activeRunCount })}</button> : null;
  const draftStudyContext = (view === "projects" || (view === "data" && dataContextId === "draft")) && !editingProjectId;
  const studyContext = runRoute ? null : draftStudyContext ? <div className="workspace-study-context"><span>{t("studies.context.draft")}</span><b>{projectForm.name}</b><small>{t("studies.context.draftNote")}</small></div> : selectedProject ? <div className="workspace-study-context"><span>{t("studies.context.selected")}</span><b>{selectedProject.name}</b><span>{selectedProject.revision_number !== undefined ? t("studies.saved.revision", { number: selectedProject.revision_number }) : t("studies.context.revisionUnknown")}</span><small>{t("studies.context.selectedNote")}</small></div> : null;
  // R-6 (P1-polish): below 900 px the top bar keeps the page title and the Read
  // me icon; the data pack, the Study context and the background Runs fold
  // into one disclosure "Study: <name>"; the service status is in the drawer.
  const disclosureName = draftStudyContext || (draftContext && view === "projects") ? projectForm.name : selectedProject?.name ?? (headerPack ? modelDisplayName(headerPack.name) : "");
  const disclosure = narrow && (packMeta || studyContext) ? <details className="topbar-study"><summary>{t("header.studyDisclosure", { name: disclosureName })}</summary><div className="topbar-study-body">{studyContext}{packMeta && <div className="top-meta">{packMeta}</div>}{backgroundRuns}</div></details> : null;
  return <WorkbenchContext.Provider value={workbench}><WorkspaceStoreProvider store={store}><div className="workbench">
    <a className="skip-link" href="#main-content">{t("shell.skipToMain")}</a>
    <header className="topbar"><div className="topbar-title"><small>{t("header.breadcrumb", { group: t(navGroupLabel(view)) })}</small><h1 ref={heading} tabIndex={-1}>{t(currentView.label)}</h1></div><div className="top-meta">
      {!narrow && packMeta}
      {!narrow && backgroundRuns}
      <button type="button" className={`secondary workspace-readme-trigger${narrow ? " icon-only" : ""}`} onClick={() => setReadMeOpen(true)} aria-haspopup="dialog" aria-label={narrow ? t("header.readMe") : undefined} title={narrow ? t("header.readMe") : undefined}>{narrow ? <svg className="readme-icon" viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" focusable="false"><circle cx="10" cy="10" r="8.25" fill="none" stroke="currentColor" strokeWidth="1.5" /><circle cx="10" cy="6.2" r="1.1" fill="currentColor" /><path d="M10 9v5.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" /></svg> : t("header.readMe")}</button>
    </div>{disclosure}</header>
    <WorkspaceRail view={view} onNavigate={openView} onRetry={() => void refresh()} service={service} />
    <main id="main-content" className="surface" tabIndex={-1}>
      <ReadMePanel open={readMeOpen} onClose={() => setReadMeOpen(false)} />
      {/* W4c: also on the Run centre, for the selected Run. */}
      {(isRunSectionView(view) || view === "runCentre") && runId && <RunSectionNav view={view} hrefFor={(section) => routePathname({ view: section, runId })} onNavigate={openView} />}
      {runRoute ? <RunContextBar run={selectedRun} frozen={{ runId: frozenRunSelectionId, status: frozenRunSelectionId === selectedRun?.id ? frozenRunProject ? "ready" : "unavailable" : "loading", project: frozenRunProject, snapshot: frozenInputSnapshot }} actions={{ onOpenInspect: (tab) => { setInspectTarget(tab ? { tab, nonce: Date.now() } : null); setView("audit"); }, onShowStressEvents: () => { setReplayTarget(null); setStressEventsFocus(Date.now()); setView("marketReplay"); } }} /> : !narrow && studyContext}
      {online && selectedRunId && isRunView && !selectedRun && <div className="notice" role="status">The requested Run is unavailable or belongs to another Study. Choose a Study and Run from Runs; no substitute result has been opened.</div>}
      {notice && <div className="notice" role="status"><span>{notice}</span><button onClick={() => setNotice("")}>{t("ui.close")}</button></div>}
      {!notice && startedRun && startedRunNoticeVisible(startedRun, { view, studyId: selectedProjectId }) && <div className="notice" role="status"><span>{startedRunNoticeText(startedRun, workspace.runs.find((run) => run.id === startedRun.runId))}</span><button onClick={() => setStartedRun(null)}>{t("ui.close")}</button></div>}
      {migrationPrompt && <StudyMigrationDialog key={migrationPrompt.nonce} projectId={migrationPrompt.projectId} studyName={migrationPrompt.studyName} migration={migrationPrompt.migration} version={health?.version} apiBase={API_BASE}
        onCancel={() => { const projectId = migrationPrompt.projectId; setMigrationPrompt(null); setNotice("The Study was not changed. It cannot run until the listed changes are confirmed."); void recheckAfterMigration(projectId, false); }}
        onSaved={(revisionNumber) => { const projectId = migrationPrompt.projectId; setMigrationPrompt(null); setPreflight(null); setNotice(`Saved as a new revision${revisionNumber ? ` (revision ${revisionNumber})` : ""}. Readiness is checked again below; then start the Run.`); void recheckAfterMigration(projectId, true); }} />}
      {children}
    </main>
  </div></WorkspaceStoreProvider></WorkbenchContext.Provider>;
}
