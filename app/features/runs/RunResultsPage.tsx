"use client";

// One Run's annual results (/runs/[runId]?year=, P1 spec 5.1 and 6.5; W4c).
// The Run centre (/runs) starts Runs; this page shows what one Run computed: a
// one-line header with the model year, the results (KPIs as Metric, the cost
// trend as a ChartFrame, tables as DataTable), the Run's status and actions
// (RunStatusPanel, the same as in the Run centre) and, for a finished Run, the
// archived-method panels.  A completed Run shows its results first; any other
// Run (running, failed, cancelled, lost) its status first.
import { useT } from "../../i18n/LocaleProvider";
import { PageHeader } from "../../ui/PageHeader.tsx";
import { isResultCoverage } from "../shared/coverageView.ts";
import { RUN_SCOPE_LABELS } from "../workspace/runScope";
import FrozenInputRecoveryPanel from "../workspace/FrozenInputRecoveryPanel";
import RunReproductionPanel from "../workspace/RunReproductionPanel";
import { AnnualResults, SmokeDiagnostics } from "./RunResults";
import RunStatusPanel, { type RunStatusActions } from "./RunStatusPanel";
import type { RunWorkspaceActions } from "./RunWorkspace";
import { isActiveRunStatus, runIdSuffix } from "./runHistoryView.ts";
import type { FrozenInputSnapshot, ModelRun, ResourceReadiness, RunMode } from "./types";
import type { Project } from "../studies/types";

const NO_FROZEN = { contextKind: "", runId: "", readiness: null, project: null, snapshot: null };

export const DIAGNOSTIC_MODES: readonly string[] = ["smoke", "two_year_smoke", "value_101_day"];

/** The model years a results page can show (recorded annual results; none for a diagnostic scope). */
export function resultYears(run: Pick<ModelRun, "mode" | "results"> | undefined): number[] {
  if (!run || DIAGNOSTIC_MODES.includes(run.mode)) return [];
  return [...new Set((run.results ?? []).map((result) => result.year))].sort((a, b) => a - b);
}

export default function RunResultsPage({ run, launching, year, onYearChange, onOpenRunCentre, onOpenInspect, onOpenArtifacts, onRecoveredStudyCreated, selectedRunSourceMutable = false, frozen = NO_FROZEN, actions }: {
  run?: ModelRun;
  launching: string;
  selectedRunSourceMutable?: boolean;
  frozen?: { contextKind: string; runId: string; readiness: ResourceReadiness | null; project: Project | null; snapshot: FrozenInputSnapshot | null };
  /** The Run's lifecycle actions; without them the status panel is not shown (tests of the results alone). */
  actions?: RunStatusActions;
  /** The year the URL names (?year=), when the Run has it. */
  year: number | null;
  onYearChange: (year: number) => void;
  onOpenRunCentre: () => void;
  onOpenInspect: () => void;
  onOpenArtifacts?: () => void;
  onRecoveredStudyCreated: RunWorkspaceActions["onRecoveredStudyCreated"];
}) {
  const t = useT();
  if (!run) return <div className="page run-results-page"><PageHeader title={t("runs.results.title")} /><div className="empty-run"><b>{t("runs.results.noRun.title")}</b><p>{t("runs.results.noRun.body")}</p><button type="button" className="secondary" onClick={onOpenRunCentre}>{t("runs.results.runCentre")}</button></div></div>;
  const years = resultYears(run);
  const scope = RUN_SCOPE_LABELS[run.mode as RunMode] ?? String(run.mode).replaceAll("_", " ");
  const completed = run.status === "completed";
  const status = actions ? <section className="panel run-results-status" aria-label={t("runs.results.status")}><RunStatusPanel run={run} launching={launching} selectedRunSourceMutable={selectedRunSourceMutable} frozen={frozen} actions={actions} /></section> : null;
  const yearSelect = years.length > 1 ? <label className="inline-select run-results-year"><span>{t("runs.results.year")}</span><select value={year ?? years.at(-1)} onChange={(event) => onYearChange(Number(event.target.value))}>{years.map((value) => <option key={value} value={value}>{value}</option>)}</select></label> : null;
  return <div className="page run-results-page">
    <PageHeader title={t("runs.results.title")} description={t("runs.results.description", { study: run.project_name, scope, suffix: runIdSuffix(run.id) })}
      actions={<>{yearSelect}<button type="button" className="secondary" onClick={onOpenRunCentre}>{t("runs.results.runCentre")}</button></>} />
    {!completed && status}
    {DIAGNOSTIC_MODES.includes(run.mode)
      ? <SmokeDiagnostics run={run} />
      : <AnnualResults key={run.id} runId={run.id} results={run.results ?? []} coverage={isResultCoverage(run.result_coverage) ? run.result_coverage : null} onOpenInspect={onOpenInspect} publication={run.result_publication} withheldYearCount={run.withheld_result_year_count} validation={run} onExportLedger={onOpenArtifacts} year={year} onYearChange={onYearChange} />}
    <button type="button" className="audit-link" onClick={onOpenInspect}>{t("runs.results.inspect")}</button>
    {completed && status}
    {/* R5 R-低3: the historical-reproduction and frozen-input panels apply to a finished Run only. */}
    {!isActiveRunStatus(run.status) && <section className="run-results-archived" aria-label={t("runs.results.archived")}><RunReproductionPanel key={run.id} runId={run.id} /><FrozenInputRecoveryPanel runId={run.id} disabled={Boolean(launching)} onStudyCreated={onRecoveredStudyCreated} /></section>}
  </div>;
}
