"use client";

// The status of one Run and what can be done with it (P1 spec 6.5, W4c):
// status word, stage and progress, validation, the lifecycle notices (worker
// exited or lost), the error code with its first diagnostic line, Resubmit,
// Resume, the copperplate fallback and the lifecycle actions. Moved unchanged
// from the Runs page; shown in the Run centre (/runs) for the selected Run and
// on the Run's own page (/runs/[runId]).
import { useT } from "../../i18n/LocaleProvider";
import { Badge } from "../shared/presentation";
import { Callout } from "../shared/Callout";
import { executionLabel, statusLabel, statusWord } from "../shared/labels.ts";
import { RUN_SCOPE_LABELS } from "../workspace/runScope";
import ReadinessEvidence from "../evidence/ReadinessEvidence";
import type { Project } from "../studies/types";
import RunErrorBox from "./RunErrorBox";
import { lifecycleNotice } from "./lifecycleView.ts";
import { snapshottingNote, preparationProgressText } from "./runHistoryView.ts";
import type { FrozenInputSnapshot, ModelRun, ResourceReadiness } from "./types";

/** R6-1 (EM-中1): the code of a Run stopped because the installed code changed after it was queued. */
export const EXECUTION_IDENTITY_CHANGED = "GF_RUN_EXECUTION_IDENTITY_CHANGED";

export type RunStatusActions = {
  resumeRun: (run: ModelRun) => Promise<void>;
  rerunAsCopperplate: (run: ModelRun) => Promise<void>;
  /** R6-1 (EM-中1): start a new Run of the same Study and scope with the installed code. */
  resubmitRun?: (run: ModelRun) => Promise<void>;
  lifecycleAction: (run: ModelRun, action: "cancel" | "archive" | "restore" | "export" | "delete") => Promise<void>;
  markLost?: (run: ModelRun) => Promise<void>;
};

export default function RunStatusPanel({ run: selectedRun, launching, selectedRunSourceMutable, frozen, actions }: {
  run: ModelRun;
  launching: string;
  selectedRunSourceMutable: boolean;
  frozen: { contextKind: string; runId: string; readiness: ResourceReadiness | null; project: Project | null; snapshot: FrozenInputSnapshot | null };
  actions: RunStatusActions;
}) {
  const t = useT();
  const { resumeRun, resubmitRun, rerunAsCopperplate, lifecycleAction, markLost } = actions;
  // R6-1 (EM-中1): stopped before it started because the installed code changed.
  const codeChangedBeforeStart = selectedRun.status === "failed" && selectedRun.error_code === EXECUTION_IDENTITY_CHANGED;
  const notice = lifecycleNotice(selectedRun);
  // A24-5: the stage and elapsed time while the Run's inputs are frozen.
  const preparationText = preparationProgressText(selectedRun);
  const selectedRunContext = { kind: frozen.contextKind };
  const frozenRunSelectionId = frozen.runId;
  const frozenRunReadiness = frozen.readiness;
  const frozenRunProject = frozen.project;
  const frozenInputSnapshot = frozen.snapshot;
  return <div className="run-status-panel">
    <div className="run-status"><div><Badge tone={selectedRun.status === "completed" ? "good" : selectedRun.status === "failed" ? "warn" : "blue"} title={selectedRun.status}>{statusWord(selectedRun.status)}</Badge><b>{selectedRun.current_stage}</b><small>{t(selectedRun.mode === "smoke" ? "runStatus.mode.smoke" : selectedRun.mode === "two_year_smoke" ? "runStatus.mode.twoYearSmoke" : selectedRun.mode === "value_101_day" ? "runStatus.mode.lesson" : selectedRun.mode === "two_year" ? "runStatus.mode.twoYear" : "runStatus.mode.full")} / {selectedRun.id}</small>{preparationText && <small className="run-preparation-progress value-new-control" role="status">{preparationText}</small>}{(selectedRun.status === "snapshotting" || preparationText) && <small className="run-launch-note value-new-control">{snapshottingNote()}</small>}</div><strong>{selectedRun.completed_years}<span> / {selectedRun.total_years}</span></strong></div>
    <div className="validation-strip">
      <span><small>{t("runStatus.execution")}</small><b>{executionLabel(selectedRun)}</b></span>
      <span><small>{t("runStatus.contract")}</small><b>{statusLabel(selectedRun.contract_validation_status)}</b></span>
      <span><small>{t(selectedRun.mode === "value_101_day" ? "runStatus.resultScope" : selectedRun.retained_comparison_role === "required_reproduction_gate" ? "runStatus.reproductionGate" : "runStatus.scientific")}</small><b>{selectedRun.mode === "value_101_day" ? t("runStatus.teaching") : statusLabel(selectedRun.scientific_scenario_status ?? selectedRun.scientific_validation_status)}</b></span>
    </div>
    {["ready", "partial"].includes(selectedRunContext.kind) && frozenRunSelectionId === selectedRun.id && frozenRunReadiness && <ReadinessEvidence readiness={frozenRunReadiness} project={frozenRunProject ?? undefined} snapshot={frozenInputSnapshot} frozen />}
    {selectedRun.source_study_status === "trash" && <div className="info-box"><b>{t("runStatus.trash.title")}</b><br />{t("runStatus.trash.body")}</div>}
    {selectedRun.source_study_status === "missing" && <div className="error-box"><b>{t("runStatus.missing.title")}</b> {t("runStatus.missing.body")}</div>}
    {selectedRun.retained_numerical_comparison_status === "expected_difference" && <div className="info-box">{t("runStatus.expectedDifference")}</div>}
    <div className="progress"><i style={{ width: `${selectedRun.total_years ? selectedRun.completed_years / selectedRun.total_years * 100 : 0}%` }} /></div>
    {selectedRun.recovery && <div className="info-box"><b>{t("runStatus.recovery.title")}</b><br />{selectedRun.recovery.latest_safe_point?.available ? t("runStatus.recovery.latest", { meaning: selectedRun.recovery.latest_safe_point.meaning ?? t("runStatus.recovery.modelYear", { year: selectedRun.recovery.latest_safe_point.year }) }) : t("runStatus.recovery.none")} {t("runStatus.recovery.body")}</div>}
    {notice?.kind === "worker_exited" && <Callout tone="caution" className="run-lifecycle-callout" title={notice.title} actions={notice.canResume ? <button type="button" className="value-action-primary" disabled={Boolean(launching) || !selectedRunSourceMutable} onClick={() => void resumeRun(selectedRun)}>{t(launching === "resume" ? "runStatus.checkingCheckpoint" : "runStatus.resume")}</button> : undefined}><p>{notice.body}</p>{notice.resumeBlockedReason && <p>{notice.resumeBlockedReason}</p>}<code>{selectedRun.error_code}</code></Callout>}
    {notice?.kind === "worker_lost" && <Callout tone="caution" className="run-lifecycle-callout" title={notice.title} actions={markLost ? <button type="button" className="value-action-primary" disabled={Boolean(launching)} onClick={() => void markLost(selectedRun)}>{t(launching === "mark-lost" ? "runStatus.marking" : "runStatus.markLost")}</button> : undefined}><p>{notice.body} {t("runStatus.markLostBody")}</p></Callout>}
    {/* Spec 6.5: the error code and the first diagnostic line; the rest on request. */}
    <RunErrorBox run={selectedRun} />
    {codeChangedBeforeStart && resubmitRun && <button className="primary full" disabled={Boolean(launching) || !selectedRunSourceMutable} onClick={() => void resubmitRun(selectedRun)}>{t(Object.hasOwn(RUN_SCOPE_LABELS, launching) ? "runStatus.starting" : "runStatus.resubmit")}</button>}
    {["failed", "cancelled"].includes(selectedRun.status) && !codeChangedBeforeStart && <button className="secondary full" disabled={Boolean(launching) || !selectedRunSourceMutable} onClick={() => void resumeRun(selectedRun)}>{t(launching === "resume" ? "runStatus.checkingCheckpoint" : "runStatus.resumeCheckpoint")}</button>}
    {selectedRun.status === "failed" && selectedRun.modules?.balancing === "value-zonal-redispatch-balancing" && <button className="secondary full" disabled={Boolean(launching) || !selectedRunSourceMutable} onClick={() => void rerunAsCopperplate(selectedRun)}>{t(launching === "rerun-copperplate" ? "runStatus.creatingRun" : "runStatus.copperplate")}</button>}
    <div className="lifecycle-actions">
      {["queued", "snapshotting", "running"].includes(selectedRun.status) && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "cancel")}>{t("runStatus.cancel")}</button>}
      {["completed", "failed", "cancelled"].includes(selectedRun.status) && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "archive")}>{t("runStatus.archive")}</button>}
      {selectedRun.status === "archived" && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "restore")}>{t("runStatus.restore")}</button>}
      {["completed", "failed", "cancelled", "archived"].includes(selectedRun.status) && <button className="secondary" disabled={Boolean(launching)} onClick={() => void lifecycleAction(selectedRun, "export")}>{t("runStatus.export")}</button>}
      {["completed", "failed", "cancelled", "archived"].includes(selectedRun.status) && <button className="secondary danger" disabled={Boolean(launching)} title={t("runs.delete.buttonTitle")} onClick={() => void lifecycleAction(selectedRun, "delete")}>{t("runs.delete.button")}</button>}
    </div>
  </div>;
}
