"use client";

import { runModesForStudy, runScopeOptionLabel, RUN_SCOPE_LABELS } from "../workspace/runScope";

import type { Workspace } from "../shared/workspaceTypes";
import type { View } from "../shared/navigation";
import type { Project, DataPack } from "../studies/types";
import type { ModelRun, RunMode, PreflightReport, DomainSection, ResourceReadiness, FrozenInputSnapshot } from "./types";
import { Badge, formatBytes, formatNumber, withUnit } from "../shared/presentation";
import { networkPackReadinessLabel } from "../learn/studyLifecycle";
import FrozenInputRecoveryPanel from "../workspace/FrozenInputRecoveryPanel";
import RunReproductionPanel from "../workspace/RunReproductionPanel";
import BaselineRuns from "../workspace/BaselineRuns";
import ComparisonWorkspace from "../results/ComparisonWorkspace";
import ReadinessEvidence from "../evidence/ReadinessEvidence";
import DomainReadinessPanel from "./DomainReadinessPanel";
import ReadinessIssues from "./ReadinessIssues";
import { AnnualResults, SmokeDiagnostics } from "./RunResults";
import { isResultCoverage } from "../shared/coverageView.ts";
import { Callout } from "../shared/Callout";
import { lifecycleNotice } from "./lifecycleView.ts";
import { preflightRunBlockedReason } from "../workspace/preflightIdentity";
import "./run-history.css";
import { studyMethodologyText, type MethodologyCatalogue } from "../studies/methodologyChoice.ts";
import { executionLabel, statusLabel } from "../shared/labels.ts";
import { RUN_FREEZE_NOTE, SNAPSHOTTING_NOTE, isActiveRunStatus, preparationProgressText, runtimeEstimateText, runHistoryEmpty, runOptionLabel, runSelectPlaceholder } from "./runHistoryView.ts";

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
  return <small>{withUnit(formatNumber(estimates.periods, 0), "periods")} · about {formatBytes(estimates.disk_bytes)} disk · about {formatBytes(estimates.peak_memory_bytes)} peak memory · {runtimeEstimateText(estimates)}</small>;
}

export default function RunWorkspace({ workspace, selectedProjectId, selectedProject, selectedProjectPack, selectedRun, projectRuns, preflight, effectivePreflightMode, checkingPreflight, zonalPreflight, teachingProject, launching, selectedRunSourceMutable, canRunMode, frozen, actions, methodologyCatalogue }: RunWorkspaceProps) {
  const { selectRunProject, onSelectRun, onMode, onNavigate, cloneStoragePolicy, checkPreflight, startRun, resumeRun, rerunAsCopperplate, lifecycleAction, onRecoveredStudyCreated, markLost } = actions;
  const notice = selectedRun ? lifecycleNotice(selectedRun) : null;
  // Spec 11.4 (M-D3): a blocked readiness check disables the Run and says why.
  const runBlockedReason = preflightRunBlockedReason(preflight);
  const recovery = selectedProject?.extensions?.frozen_recovery;
  // R-D2 / S-D12: launching holds the scope while a Run is being started.
  const startingRun = Object.hasOwn(RUN_SCOPE_LABELS, launching);
  const emptyHistory = runHistoryEmpty(projectRuns.length, startingRun);
  // A24-5: the stage and elapsed time while the Run's inputs are frozen.
  const preparationText = selectedRun ? preparationProgressText(selectedRun) : null;
  const selectedRunContext = { kind: frozen.contextKind };
  const frozenRunSelectionId = frozen.runId;
  const frozenRunReadiness = frozen.readiness;
  const frozenRunProject = frozen.project;
  const frozenInputSnapshot = frozen.snapshot;
  return <div className="page">
      {/* R5 R-低3: the historical-reproduction and frozen-input panels apply to a finished Run only. */}
      {selectedRun && !isActiveRunStatus(selectedRun.status) && <><RunReproductionPanel key={selectedRun.id} runId={selectedRun.id} /><FrozenInputRecoveryPanel runId={selectedRun.id} disabled={Boolean(launching)} onStudyCreated={onRecoveredStudyCreated} /></>}
      {recovery && <section className="panel journey-origin" aria-label="Frozen input Study origin"><b>{recovery.recovery_mode === "strict" ? "严格核对冻结输入" : "冻结输入按当前方法迁移"} · 已保存独立 Study</b><p>来源 Run：<code>{recovery.source_run_id}</code> · 来源快照：<code>{recovery.source_snapshot_id}</code>。迁移或身份核对不表示历史环境已恢复，也不恢复检查点。</p><p>锁定范围：<code>{recovery.required_mode}</code> · {recovery.scope.start_year}–{recovery.scope.end_year} · 每年 {recovery.scope.periods_per_year} 时段。先 Check readiness，再明确启动。</p><details><summary>已接受执行身份</summary><code>{recovery.accepted_execution_identity_sha256}</code></details>{!effectivePreflightMode && <p role="alert">锁定范围与数据包允许范围不相容；不能 readiness 或启动。</p>}</section>}
      {!recovery && selectedProject?.derivation && <section className="panel journey-origin" aria-label="Study origin">
        <div><b>{selectedProject.derivation.intent === "edit_module" ? "方法对照研究" : selectedProject.derivation.intent === "data" ? "换数据研究" : "复现研究"} · 已保存独立 Study</b><p>来源 Study：<code>{selectedProject.derivation.source_study_id}</code>。先选择范围、Check readiness，再明确启动。比较前核对运行范围及输入和方法差异。</p>
          {selectedProject.derivation.method_change && <p>修改槽位：<code>{selectedProject.derivation.method_change.slot}</code> · {selectedProject.derivation.method_change.source_module_id} → {selectedProject.derivation.method_change.module_id}</p>}<details><summary>来源版本</summary><code>{selectedProject.derivation.source_revision_sha256}</code></details></div>
        <BaselineRuns sourceStudyId={selectedProject.derivation.source_study_id} sourceRevision={selectedProject.derivation.source_revision_sha256} runs={workspace.runs} onSelect={(run) => { selectRunProject(run.project_id); onSelectRun(run.id); }} /><div className="journey-origin-actions"><button className="secondary" onClick={() => selectRunProject(selectedProject.derivation!.source_study_id)}>查看基线 Study 的全部 Runs</button><button className="secondary" onClick={() => document.getElementById("comparison-title")?.scrollIntoView({ block: "start", behavior: "smooth" })}>选择对照 Runs</button></div>
      </section>}
      <div className="page-title"><div><span>Run a study</span><h2>Check the setup, then let the model advance</h2><p>A scientific run clears every half-hour period, records the annual investment and planning decisions, and passes the updated state into the next year.</p></div><Badge tone={selectedRun?.status === "completed" ? "good" : selectedRun?.status === "failed" ? "warn" : "blue"}>{selectedRun?.status ?? "No run selected"}</Badge></div>
      <div className="run-layout">
        <section className="panel run-control">
          <div className="panel-head"><div><span>Selected study</span><h3>What will run</h3></div></div>
          <label><span>Study</span><select value={selectedProjectId} onChange={(event) => selectRunProject(event.target.value)}><option value="">Choose a saved study</option>{selectedProjectId && !selectedProject && <option value={selectedProjectId}>Source Study in trash</option>}{workspace.projects.map((project) => <option value={project.id} key={project.id}>{project.name}</option>)}</select></label>
          {selectedProject ? <div className="project-summary"><div><span>Years</span><b>{selectedProject.start_year} to {selectedProject.end_year}</b></div><div><span>Data pack</span><b>{selectedProject.data_pack_id}</b></div><div><span>Methodology</span><b title={studyMethodologyText(selectedProject.parameters, methodologyCatalogue).profileId ?? undefined}>{studyMethodologyText(selectedProject.parameters, methodologyCatalogue).label}</b></div><div><span>Annual sequence</span><b>Planning → PSM → caps → investment → admission → next year</b></div></div> : <p className="empty-copy">Save a study before starting a run.</p>}
          {selectedProject?.modules.balancing === "value-zonal-redispatch-balancing" && <section className="run-network-readiness"><header><div><span>Optional zonal method</span><b>Signed network input required</b></div><Badge tone={zonalPreflight?.status === "data_ready" ? "good" : "warn"}>{!preflight ? "Run preflight" : zonalPreflight?.status === "data_ready" ? "Signed network ready" : "Network check required"}</Badge></header><dl><div><dt>Data pack</dt><dd>{selectedProject.data_pack_id} · {selectedProjectPack?.complete ? "base roles complete" : "base roles incomplete"}</dd></div><div><dt>Network pack</dt><dd>{networkPackReadinessLabel(zonalPreflight)}</dd></div><div><dt>Demand authority</dt><dd>{selectedProject.market_configuration?.zonal_demand_mode === "scenario_scaled_zonal_shares" ? "Research-pack national demand × network zonal shares" : selectedProject.market_configuration?.zonal_demand_mode === "network_pack_absolute_demand" ? "Network-pack absolute zonal demand" : "Missing — Study revision must be updated"}</dd></div><div><dt>Market sequence</dt><dd>National ahead → zonal redispatch</dd></div><div><dt>Physics</dt><dd>Lossless fixed computational corridors</dd></div><div><dt>Asset mapping</dt><dd>Frozen zone; documented fallback for unresolved assets</dd></div>{preflight && <div><dt>Estimated result disk</dt><dd>{formatBytes(preflight.estimates.disk_bytes)}</dd></div>}</dl><small>The preflight checks the signed network-pack identity. This method does not perform N-1, voltage or dynamic-security analysis.</small></section>}
          {!recovery && selectedProject && selectedProject.modules.psm === "value-bid-at-cost-psm" && <details className="diagnostic-actions"><summary>Clone a storage-pricing experiment</summary><p>Create a controlled study that changes only the storage offer-cost module. Perfect-foresight co-optimisation is a different PSM formulation and is not presented as a tariff.</p>{workspace.modules.filter((module) => module.slot === "storage_cost").map((module) => <button className="text-button full" key={module.id} disabled={Boolean(launching) || selectedProject.modules.storage_cost === module.id} onClick={() => void cloneStoragePolicy(module.id)}>{selectedProject.modules.storage_cost === module.id ? `Current: ${module.name}` : `Clone with ${module.name}`}</button>)}</details>}
          <div className="preflight-card"><div><label><span>Check for</span><select value={effectivePreflightMode ?? ""} disabled={!effectivePreflightMode} onChange={(event) => { onMode(event.target.value as RunMode); }}>{!effectivePreflightMode && <option value="">没有可用范围</option>}{runModesForStudy(selectedProject, selectedProjectPack).map((mode) => <option key={mode} value={mode}>{runScopeOptionLabel(mode, selectedProject)}</option>)}</select></label><button className="secondary" disabled={!selectedProject || checkingPreflight || !effectivePreflightMode} onClick={() => void checkPreflight(effectivePreflightMode ?? undefined)}>{checkingPreflight ? "Checking…" : "Check readiness"}</button></div>{preflight && <section className={preflight.accepted ? "accepted" : "blocked"}><header><b>{preflight.accepted ? "Ready" : "Needs attention"}</b><PreflightEstimates estimates={preflight.estimates} /></header><ReadinessIssues errors={preflight.errors} warnings={preflight.warnings} />{!preflight.errors.length && !preflight.warnings.length && <small>Runtime, modules, data, parameters, disk and selected outputs passed the check.</small>}</section>}{preflight?.resource_readiness && <ReadinessEvidence readiness={preflight.resource_readiness} project={selectedProject} />}{preflight?.checks?.domain_readiness && <DomainReadinessPanel readiness={preflight.checks.domain_readiness} onNavigate={onNavigate} runBlocked={!preflight.accepted} />}</div>
          <div className="primary-run-actions">
            <button type="button" className="primary full" disabled={!selectedProject || !effectivePreflightMode || Boolean(launching) || !workspace.runtime.compatible || checkingPreflight || Boolean(runBlockedReason)} aria-describedby={runBlockedReason ? "run-blocked-reason" : undefined} onClick={() => { if (effectivePreflightMode) void startRun(effectivePreflightMode); }}>{launching ? "Starting…" : `Run selected scope · ${effectivePreflightMode ? RUN_SCOPE_LABELS[effectivePreflightMode] : "unavailable"}`}</button>
            {runBlockedReason && <p id="run-blocked-reason" className="readiness-run-blocked" role="status">{runBlockedReason}</p>}
            {startingRun && <p className="run-launch-note value-new-control" role="status">{RUN_FREEZE_NOTE}</p>}
            <small>The scope selected above is used for both readiness and this Run. Two-period and hand-off checks test wiring; the one-day lesson runs 48 half-hours through the PSM. Full scopes include the annual sequence.</small>
          </div>
          {!workspace.runtime.compatible && <div className="error-box">The VALUE native capability is unavailable. Run the environment doctor for the exact missing interpreter or package.</div>}
          <small className="run-warning">Full studies may take several hours. Closing this page does not stop a background run.</small>
        </section>
        <section className="panel run-results">
          <div className="panel-head"><div><span>Run history</span><h3>Progress and results</h3></div><select aria-label="Selected run" value={selectedRun?.id ?? ""} onChange={(event) => onSelectRun(event.target.value)}>{(!selectedRun || !projectRuns.length) && <option value="" disabled={projectRuns.length > 0}>{runSelectPlaceholder(projectRuns.length)}</option>}{projectRuns.map((run) => <option value={run.id} key={run.id} title={run.id}>{runOptionLabel(run)}</option>)}</select></div>
          {selectedRun ? <>
            <div className="run-status"><div><Badge tone={selectedRun.status === "completed" ? "good" : selectedRun.status === "failed" ? "warn" : "blue"}>{selectedRun.status}</Badge><b>{selectedRun.current_stage}</b><small>{selectedRun.mode === "smoke" ? "Two-period verification" : selectedRun.mode === "two_year_smoke" ? "Two-year smoke test" : selectedRun.mode === "value_101_day" ? "One-day market lesson" : selectedRun.mode === "two_year" ? "Complete two-year model" : "Complete project"} / {selectedRun.id}</small>{preparationText && <small className="run-preparation-progress value-new-control" role="status">{preparationText}</small>}{(selectedRun.status === "snapshotting" || preparationText) && <small className="run-launch-note value-new-control">{SNAPSHOTTING_NOTE}</small>}</div><strong>{selectedRun.completed_years}<span> / {selectedRun.total_years}</span></strong></div>
            <div className="validation-strip">
              <span><small>Execution</small><b>{executionLabel(selectedRun)}</b></span>
              <span><small>Contract check</small><b>{statusLabel(selectedRun.contract_validation_status)}</b></span>
              <span><small>{selectedRun.mode === "value_101_day" ? "Result scope" : selectedRun.retained_comparison_role === "required_reproduction_gate" ? "Reproduction gate" : "Scientific scenario"}</small><b>{selectedRun.mode === "value_101_day" ? "Teaching diagnostic" : statusLabel(selectedRun.scientific_scenario_status ?? selectedRun.scientific_validation_status)}</b></span>
            </div>
            {["ready", "partial"].includes(selectedRunContext.kind) && frozenRunSelectionId === selectedRun.id && frozenRunReadiness && <ReadinessEvidence readiness={frozenRunReadiness} project={frozenRunProject ?? undefined} snapshot={frozenInputSnapshot} frozen />}
            {selectedRun.source_study_status === "trash" && <div className="info-box"><b>Source Study in trash</b><br />Results and audit exports remain readable. Restore the Study before resuming, cloning or creating another Run from it.</div>}
            {selectedRun.source_study_status === "missing" && <div className="error-box"><b>Source Study missing.</b> Results remain readable. Frozen input review can create an independent Study when retained evidence permits it; other derived Run actions are disabled.</div>}
            {selectedRun.retained_numerical_comparison_status === "expected_difference" && <div className="info-box">This project selected a different storage-cost policy. Its retained VALUE numerical difference is expected and reported; it is not a failed scientific scenario.</div>}
            <div className="progress"><i style={{ width: `${selectedRun.total_years ? selectedRun.completed_years / selectedRun.total_years * 100 : 0}%` }} /></div>
            {selectedRun.recovery && <div className="info-box"><b>Recovery: annual boundaries</b><br />{selectedRun.recovery.latest_safe_point?.available ? `Latest verified opening state: ${selectedRun.recovery.latest_safe_point.meaning ?? `model year ${selectedRun.recovery.latest_safe_point.year}`}.` : "No verified annual checkpoint is available yet."} An interrupted model year is recomputed; subannual resume is not currently supported. If historical execution evidence is unavailable, review frozen inputs and explicitly migrate to a fresh Study using the current method.</div>}
            {notice?.kind === "worker_exited" && <Callout tone="caution" className="run-lifecycle-callout" title={notice.title} actions={notice.canResume ? <button type="button" className="value-action-primary" disabled={Boolean(launching) || !selectedRunSourceMutable} onClick={() => void resumeRun(selectedRun)}>{launching === "resume" ? "Checking checkpoint…" : "Resume"}</button> : undefined}><p>{notice.body}</p>{notice.resumeBlockedReason && <p>{notice.resumeBlockedReason}</p>}<code>{selectedRun.error_code}</code></Callout>}
            {notice?.kind === "worker_lost" && <Callout tone="caution" className="run-lifecycle-callout" title={notice.title} actions={markLost ? <button type="button" className="value-action-primary" disabled={Boolean(launching)} onClick={() => void markLost(selectedRun)}>{launching === "mark-lost" ? "Marking…" : "Mark as lost"}</button> : undefined}><p>{notice.body} Marking it lost records the Run as failed so that it can be resumed; VALUE asks you to confirm first.</p></Callout>}
            {selectedRun.error && <div className="error-box">{selectedRun.error_code && <b>{selectedRun.error_code}: </b>}{selectedRun.error}</div>}
            {["failed", "cancelled"].includes(selectedRun.status) && <button className="secondary full" disabled={Boolean(launching) || !selectedRunSourceMutable} onClick={() => void resumeRun(selectedRun)}>{launching === "resume" ? "Checking checkpoint..." : "Resume from verified annual checkpoint with the same physics"}</button>}
            {selectedRun.status === "failed" && selectedRun.modules?.balancing === "value-zonal-redispatch-balancing" && <button className="secondary full" disabled={Boolean(launching) || !selectedRunSourceMutable} onClick={() => void rerunAsCopperplate(selectedRun)}>{launching === "rerun-copperplate" ? "Creating a new run…" : "Create a new copperplate fallback run"}</button>}
            <div className="lifecycle-actions">
              {["queued", "snapshotting", "running"].includes(selectedRun.status) && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "cancel")}>Request safe cancellation</button>}
              {["completed", "failed", "cancelled"].includes(selectedRun.status) && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "archive")}>Archive</button>}
              {selectedRun.status === "archived" && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "restore")}>Restore archive</button>}
              {["completed", "failed", "cancelled", "archived"].includes(selectedRun.status) && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "export")}>Prepare audit bundle</button>}
              {["completed", "failed", "cancelled", "archived"].includes(selectedRun.status) && <button className="secondary danger" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "delete")}>Move to trash</button>}
            </div>
            {["smoke", "two_year_smoke", "value_101_day"].includes(selectedRun.mode) ? <SmokeDiagnostics run={selectedRun} /> : <AnnualResults key={selectedRun.id} runId={selectedRun.id} results={selectedRun.results ?? []} coverage={isResultCoverage(selectedRun.result_coverage) ? selectedRun.result_coverage : null} onOpenInspect={() => onNavigate("audit")} publication={selectedRun.result_publication} withheldYearCount={selectedRun.withheld_result_year_count} validation={selectedRun} onExportLedger={actions.openInspect ? () => actions.openInspect?.("artifacts") : undefined} />}
            <button className="audit-link" onClick={() => onNavigate("audit")}>Inspect planning projects and market clearing</button>
          </> : <div className="empty-run"><b>{emptyHistory.title}</b><p>{emptyHistory.body}</p></div>}
        </section>
      </div>
      <ComparisonWorkspace runs={workspace.runs} />
    </div>;
}