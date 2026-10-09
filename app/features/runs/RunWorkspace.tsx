"use client";

import { statusWord } from "../shared/labels.ts";
import { runModesForStudy, runScopeOptionLabel, RUN_SCOPE_LABELS } from "../workspace/runScope";

import type { Workspace } from "../shared/workspaceTypes";
import type { View } from "../shared/navigation";
import type { Project, DataPack } from "../studies/types";
import type { ModelRun, RunMode, PreflightReport, DomainSection, ResourceReadiness, FrozenInputSnapshot } from "./types";
import { Badge, formatBytes, formatNumber } from "../shared/presentation";
import { networkPackReadinessLabel } from "../learn/studyLifecycle";
import BaselineRuns from "../workspace/BaselineRuns";
import ReadinessEvidence from "../evidence/ReadinessEvidence";
import DomainReadinessPanel from "./DomainReadinessPanel";
import ReadinessIssues from "./ReadinessIssues";
import { preflightRunBlockedReason } from "../workspace/preflightIdentity";
import "./run-history.css";
import { studyMethodologyText, type MethodologyCatalogue } from "../studies/methodologyChoice.ts";
import { runFreezeNote, runtimeEstimateText, runHistoryEmpty, runOptionLabel, runSelectPlaceholder } from "./runHistoryView.ts";
import { useT } from "../../i18n/LocaleProvider";
import { PageHeader } from "../../ui/PageHeader.tsx";
import RunHistoryTable from "./RunHistoryTable";
import RunStatusPanel from "./RunStatusPanel";

export type RunWorkspaceActions = {
  onRecoveredStudyCreated: (projectId: string, mode: string) => Promise<void>;
  selectRunProject: (projectId: string) => void;
  onSelectRun: (runId: string) => void;
  onMode: (mode: RunMode) => void;
  onNavigate: (view: View) => void;
  cloneStoragePolicy: (moduleId: string) => Promise<void>;
  checkPreflight: (mode?: RunMode) => Promise<void>;
  startRun: (mode: RunMode) => Promise<void>;
  resumeRun: (run: ModelRun) => Promise<void>;
  rerunAsCopperplate: (run: ModelRun) => Promise<void>;
  /** R6-1 (EM-中1): start a new Run of the same Study and scope with the installed code. */
  resubmitRun?: (run: ModelRun) => Promise<void>;
  lifecycleAction: (run: ModelRun, action: "cancel" | "archive" | "restore" | "export" | "delete") => Promise<void>;
  markLost?: (run: ModelRun) => Promise<void>;
  /** Open Inspect on one tab (spec 2.3 / 4.2: residuals, ledger export). */
  openInspect?: (tab: "planning" | "market" | "artifacts") => void;
};

type RunWorkspaceProps = {
  workspace: Pick<Workspace, "projects" | "runs" | "modules" | "runtime">;
  selectedProjectId: string;
  selectedProject?: Project;
  selectedProjectPack?: DataPack;
  selectedRun?: ModelRun;
  projectRuns: ModelRun[];
  preflight: PreflightReport | null;
  effectivePreflightMode: RunMode | null;
  checkingPreflight: boolean;
  zonalPreflight?: DomainSection;
  teachingProject: boolean;
  launching: string;
  selectedRunSourceMutable: boolean;
  canRunMode: (mode: RunMode) => boolean;
  frozen: { contextKind: string; runId: string; readiness: ResourceReadiness | null; project: Project | null; snapshot: FrozenInputSnapshot | null };
  actions: RunWorkspaceActions;
  /** R5 R-中1: names the methodology the selected Study runs under. */
  methodologyCatalogue?: MethodologyCatalogue | null;
};

/** Preflight resource estimates (R3-03): a missing runtime says so instead of "0 hours" or "— hours". */
export function PreflightEstimates({ estimates }: { estimates: PreflightReport["estimates"] }) {
  const t = useT();
  const periods = formatNumber(estimates.periods, 0);
  // Missing reads "—" on its own (withUnit's rule), never "— periods".
  return <small>{t("runCentre.estimates", { periods: periods === "—" ? "—" : t("runCentre.estimates.periods", { count: periods }), disk: formatBytes(estimates.disk_bytes), memory: formatBytes(estimates.peak_memory_bytes), runtime: runtimeEstimateText(estimates) })}</small>;
}

export default function RunWorkspace({ workspace, selectedProjectId, selectedProject, selectedProjectPack, selectedRun, projectRuns, preflight, effectivePreflightMode, checkingPreflight, zonalPreflight, teachingProject, launching, selectedRunSourceMutable, canRunMode, frozen, actions, methodologyCatalogue }: RunWorkspaceProps) {
  const { selectRunProject, onSelectRun, onMode, onNavigate, cloneStoragePolicy, checkPreflight, startRun, resumeRun, resubmitRun, rerunAsCopperplate, lifecycleAction, markLost } = actions;
  const t = useT();
  // Spec 11.4 (M-D3): a blocked readiness check disables the Run and says why.
  const runBlockedReason = preflightRunBlockedReason(preflight);
  const recovery = selectedProject?.extensions?.frozen_recovery;
  // R-D2 / S-D12: launching holds the scope while a Run is being started.
  const startingRun = Object.hasOwn(RUN_SCOPE_LABELS, launching);
  const emptyHistory = runHistoryEmpty(projectRuns.length, startingRun);
  return <div className="page">
      {/* W4c (spec 5.1/6.5): this is the Run centre (/runs). A Run's results, and its
          historical-reproduction and frozen-input panels, are on /runs/[runId]. */}
      <PageHeader title={t("runs.centre.title")} description={t("runs.centre.description")} actions={<><Badge tone={selectedRun?.status === "completed" ? "good" : selectedRun?.status === "failed" ? "warn" : "blue"} title={selectedRun?.status}>{selectedRun ? statusWord(selectedRun.status) : t("runCentre.noRunSelected")}</Badge><button type="button" className="secondary" onClick={() => onNavigate("compare")}>{t("runs.centre.compare")}</button></>} />
      {recovery && <section className="panel journey-origin" aria-label={t("runCentre.recovery.label")}><b>{t("runCentre.recovery.saved", { mode: t(recovery.recovery_mode === "strict" ? "runCentre.recovery.strict" : "runCentre.recovery.migrated") })}</b><p>{t("runCentre.recovery.sourceRun")}<code>{recovery.source_run_id}</code>{t("runCentre.recovery.sourceSnapshot")}<code>{recovery.source_snapshot_id}</code>{t("runCentre.recovery.notRestored")}</p><p>{t("runCentre.recovery.lockedScope")}<code>{recovery.required_mode}</code>{t("runCentre.recovery.scope", { start: recovery.scope.start_year, end: recovery.scope.end_year, periods: recovery.scope.periods_per_year })}</p><details><summary>{t("runCentre.recovery.identity")}</summary><code>{recovery.accepted_execution_identity_sha256}</code></details>{!effectivePreflightMode && <p role="alert">{t("runCentre.recovery.incompatible")}</p>}</section>}
      {!recovery && selectedProject?.derivation && <section className="panel journey-origin" aria-label={t("runCentre.origin.label")}>
        <div><b>{t("runCentre.recovery.saved", { mode: t(selectedProject.derivation.intent === "edit_module" ? "runCentre.origin.editModule" : selectedProject.derivation.intent === "data" ? "runCentre.origin.data" : "runCentre.origin.reproduce") })}</b><p>{t("runCentre.origin.sourceStudy")}<code>{selectedProject.derivation.source_study_id}</code>{t("runCentre.origin.next")}</p>
          {selectedProject.derivation.method_change && <p>{t("runCentre.origin.changedSlot")}<code>{selectedProject.derivation.method_change.slot}</code> · {selectedProject.derivation.method_change.source_module_id} → {selectedProject.derivation.method_change.module_id}</p>}<details><summary>{t("runCentre.origin.sourceRevision")}</summary><code>{selectedProject.derivation.source_revision_sha256}</code></details></div>
        <BaselineRuns sourceStudyId={selectedProject.derivation.source_study_id} sourceRevision={selectedProject.derivation.source_revision_sha256} runs={workspace.runs} onSelect={(run) => { selectRunProject(run.project_id); onSelectRun(run.id); }} /><div className="journey-origin-actions"><button className="secondary" onClick={() => selectRunProject(selectedProject.derivation!.source_study_id)}>{t("runCentre.origin.allBaselineRuns")}</button><button className="secondary" onClick={() => onNavigate("compare")}>{t("runCentre.origin.chooseCompare")}</button></div>
      </section>}
      <div className="run-layout">
        <section className="panel run-control">
          <div className="panel-head"><div><span>{t("runCentre.study.kicker")}</span><h3>{t("runCentre.study.title")}</h3></div></div>
          <label><span>{t("runCentre.study.label")}</span><select value={selectedProjectId} onChange={(event) => selectRunProject(event.target.value)}><option value="">{t("runCentre.study.choose")}</option>{selectedProjectId && !selectedProject && <option value={selectedProjectId}>{t("runCentre.study.inTrash")}</option>}{workspace.projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label>
          {selectedProject ? <div className="project-summary"><div><span>{t("runCentre.study.years")}</span><b>{t("runCentre.study.yearRange", { start: selectedProject.start_year, end: selectedProject.end_year })}</b></div><div><span>{t("runCentre.study.dataPack")}</span><b>{selectedProject.data_pack_id}</b></div><div><span>{t("runCentre.study.methodology")}</span><b title={studyMethodologyText(selectedProject.parameters, methodologyCatalogue, t).profileId ?? undefined}>{studyMethodologyText(selectedProject.parameters, methodologyCatalogue, t).label}</b></div><div><span>{t("runCentre.study.sequence")}</span><b>{t("runCentre.study.sequenceValue")}</b></div></div> : <p className="empty-copy">{t("runCentre.study.saveFirst")}</p>}
          {selectedProject?.modules.balancing === "value-zonal-redispatch-balancing" && <section className="run-network-readiness"><header><div><span>{t("runCentre.zonal.kicker")}</span><b>{t("runCentre.zonal.title")}</b></div><Badge tone={zonalPreflight?.status === "data_ready" ? "good" : "warn"}>{t(!preflight ? "runCentre.zonal.runPreflight" : zonalPreflight?.status === "data_ready" ? "runCentre.zonal.ready" : "runCentre.zonal.checkRequired")}</Badge></header><dl><div><dt>{t("runCentre.zonal.dataPack")}</dt><dd>{t(selectedProjectPack?.complete ? "runCentre.zonal.baseComplete" : "runCentre.zonal.baseIncomplete", { pack: selectedProject.data_pack_id })}</dd></div><div><dt>{t("runCentre.zonal.networkPack")}</dt><dd>{networkPackReadinessLabel(zonalPreflight)}</dd></div><div><dt>{t("runCentre.zonal.demand")}</dt><dd>{t(selectedProject.market_configuration?.zonal_demand_mode === "scenario_scaled_zonal_shares" ? "runCentre.zonal.demandScaled" : selectedProject.market_configuration?.zonal_demand_mode === "network_pack_absolute_demand" ? "runCentre.zonal.demandAbsolute" : "runCentre.zonal.demandMissing")}</dd></div><div><dt>{t("runCentre.zonal.sequence")}</dt><dd>{t("runCentre.zonal.sequenceValue")}</dd></div><div><dt>{t("runCentre.zonal.physics")}</dt><dd>{t("runCentre.zonal.physicsValue")}</dd></div><div><dt>{t("runCentre.zonal.mapping")}</dt><dd>{t("runCentre.zonal.mappingValue")}</dd></div>{preflight && <div><dt>{t("runCentre.zonal.disk")}</dt><dd>{formatBytes(preflight.estimates.disk_bytes)}</dd></div>}</dl><small>{t("runCentre.zonal.note")}</small></section>}
          {!recovery && selectedProject && selectedProject.modules.psm === "value-bid-at-cost-psm" && <details className="diagnostic-actions"><summary>{t("runCentre.storage.summary")}</summary><p>{t("runCentre.storage.body")}</p>{workspace.modules.filter((module) => module.slot === "storage_cost").map((module) => <button className="text-button full" key={module.id} disabled={Boolean(launching) || selectedProject.modules.storage_cost === module.id} onClick={() => void cloneStoragePolicy(module.id)}>{t(selectedProject.modules.storage_cost === module.id ? "runCentre.storage.current" : "runCentre.storage.clone", { name: module.name })}</button>)}</details>}
          <div className="preflight-card"><div><label><span>{t("runCentre.preflight.checkFor")}</span><select value={effectivePreflightMode ?? ""} disabled={!effectivePreflightMode} onChange={(event) => { onMode(event.target.value as RunMode); }}>{!effectivePreflightMode && <option value="">{t("runCentre.preflight.noScope")}</option>}{runModesForStudy(selectedProject, selectedProjectPack).map((mode) => <option key={mode} value={mode}>{runScopeOptionLabel(mode, selectedProject)}</option>)}</select></label><button className="secondary" disabled={!selectedProject || checkingPreflight || !effectivePreflightMode} onClick={() => void checkPreflight(effectivePreflightMode ?? undefined)}>{t(checkingPreflight ? "runCentre.preflight.checking" : "runCentre.preflight.check")}</button></div>{preflight && <section className={preflight.accepted ? "accepted" : "blocked"}><header><b>{t(preflight.accepted ? "runCentre.preflight.ready" : "runCentre.preflight.attention")}</b><PreflightEstimates estimates={preflight.estimates} /></header><ReadinessIssues errors={preflight.errors} warnings={preflight.warnings} />{!preflight.errors.length && !preflight.warnings.length && <small>{t("runCentre.preflight.passed")}</small>}</section>}{preflight?.resource_readiness && <ReadinessEvidence readiness={preflight.resource_readiness} project={selectedProject} />}{preflight?.checks?.domain_readiness && <DomainReadinessPanel readiness={preflight.checks.domain_readiness} onNavigate={onNavigate} runBlocked={!preflight.accepted} />}</div>
          <div className="primary-run-actions">
            <button type="button" className="primary full" disabled={!selectedProject || !effectivePreflightMode || Boolean(launching) || !workspace.runtime.compatible || checkingPreflight || Boolean(runBlockedReason)} aria-describedby={runBlockedReason ? "run-blocked-reason" : undefined} onClick={() => { if (effectivePreflightMode) void startRun(effectivePreflightMode); }}>{launching ? t("runCentre.run.starting") : t("runCentre.run.button", { scope: effectivePreflightMode ? RUN_SCOPE_LABELS[effectivePreflightMode] : t("runCentre.run.unavailable") })}</button>
            {runBlockedReason && <p id="run-blocked-reason" className="readiness-run-blocked" role="status">{runBlockedReason}</p>}
            {startingRun && <p className="run-launch-note value-new-control" role="status">{runFreezeNote()}</p>}
            <small>{t("runCentre.run.scopeNote")}</small>
          </div>
          {!workspace.runtime.compatible && <div className="error-box">{t("runCentre.runtimeUnavailable")}</div>}
          <small className="run-warning">{t("runCentre.duration")}</small>
        </section>
        <section className="panel run-results">
          <div className="panel-head"><div><span>{t("runCentre.history.kicker")}</span><h3>{t("runCentre.history.title")}</h3></div><select aria-label={t("runCentre.history.select")} value={selectedRun?.id ?? ""} onChange={(event) => onSelectRun(event.target.value)}>{(!selectedRun || !projectRuns.length) && <option value="" disabled={projectRuns.length > 0}>{runSelectPlaceholder(projectRuns.length)}</option>}{projectRuns.map((run) => <option value={run.id} key={run.id} title={run.id}>{runOptionLabel(run)}</option>)}</select></div>
          {selectedRun ? <>
            <RunStatusPanel run={selectedRun} launching={launching} selectedRunSourceMutable={selectedRunSourceMutable} frozen={frozen} actions={{ resumeRun, resubmitRun, rerunAsCopperplate, lifecycleAction, markLost }} />
            <button type="button" className="primary run-open-results" onClick={() => onNavigate("run")}>{t("runs.centre.openResults")}</button>
          </> : <div className="empty-run"><b>{emptyHistory.title}</b><p>{emptyHistory.body}</p></div>}
          <RunHistoryTable runs={projectRuns} selectedRunId={selectedRun?.id ?? ""} onOpen={(runId) => { onSelectRun(runId); onNavigate("run"); }} />
        </section>
      </div>
    </div>;
}