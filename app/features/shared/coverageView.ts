// Annual-coverage presentation (spec 4.2 / 4.4 / 4.6; P0-9 S5/S6).
// The verdict comes from the backend (gridform_core/result_coverage.py); this
// module only turns it into a pill, a sentence and the publish/withhold rule.
import { formatNumber } from "./format.ts";
import { valueStateText, type ValueStateKey } from "./valueStates.ts";
import type { PillTone } from "./Callout.tsx";
import { localizedTable, tr, type MessageKey } from "../../i18n/index.ts";

export type AnnualStatus = "complete" | "partial" | "non_annual" | "in_progress" | "invalid";

export type ResultCoverage = {
  schema_version?: string;
  annual_status: AnnualStatus;
  reason_code: string;
  coverage_fraction: number | null;
  coverage_percent: number | null;
  expected_years?: number[];
  observed_years?: number[];
  years?: { year: number; first_period: number; last_period: number; period_count: number; coverage_fraction: number; complete: boolean }[];
  coverage_source?: string;
};

export type CoveragePill = { tone: PillTone; text: string; title: string };

/** Sentences of the annual-coverage reason codes (also used by reasonCodes.ts for result queries). */
// P1 W5: dictionary messages (coverage.reason.*) in the interface language.
export const COVERAGE_REASON_KEYS = {
  annual_evidence_withheld_for_nonannual_run: "coverage.reason.annual_evidence_withheld_for_nonannual_run",
  run_in_progress: "coverage.reason.run_in_progress",
  run_cancelled_before_full_coverage: "coverage.reason.run_cancelled_before_full_coverage",
  run_failed_before_full_coverage: "coverage.reason.run_failed_before_full_coverage",
  annual_year_set_mismatch: "coverage.reason.annual_year_set_mismatch",
  annual_period_boundary_incomplete: "coverage.reason.annual_period_boundary_incomplete",
  annual_coverage_complete: "coverage.reason.annual_coverage_complete",
} as const satisfies Record<string, MessageKey>;
export const COVERAGE_REASON_TEXT: Readonly<Record<string, string>> = localizedTable(COVERAGE_REASON_KEYS);

export function isResultCoverage(value: unknown): value is ResultCoverage {
  return typeof value === "object" && value !== null
    && ["complete", "partial", "non_annual", "in_progress", "invalid"].includes(String((value as ResultCoverage).annual_status));
}

export function coverageReasonText(coverage: ResultCoverage | null | undefined): string {
  if (!coverage) return tr("coverage.notRecordedReason");
  return COVERAGE_REASON_TEXT[coverage.reason_code] ?? coverage.reason_code.replaceAll("_", " ");
}

const STOPPED_REASONS = new Set(["run_cancelled_before_full_coverage", "run_failed_before_full_coverage"]);

/** True when the verdict is "partial" because the Run was cancelled or failed. */
export function isStoppedCoverage(coverage: ResultCoverage | null | undefined): boolean {
  return coverage?.annual_status === "partial" && STOPPED_REASONS.has(coverage.reason_code);
}

/**
 * Designer ruling 2: the state word of a year whose totals are not shown.
 * "Withheld" is reserved for Q14 (a reproduction run that did not pass its raw
 * invariants); coverage gaps use their own words.
 */
export function coverageStateKey(coverage: ResultCoverage | null | undefined): ValueStateKey {
  if (!coverage) return "not_recorded";
  switch (coverage.annual_status) {
    case "non_annual": return "non_annual";
    case "in_progress": return "in_progress";
    case "invalid": return "invalid";
    default: return isStoppedCoverage(coverage) ? "stopped" : "partial_year";
  }
}

/** Coverage percentage of one year (falls back to the Run's percentage). */
export function yearCoveragePercent(coverage: ResultCoverage | null | undefined, year: number): number | null {
  const row = coverage?.years?.find((item) => item.year === year);
  return row ? row.coverage_fraction * 100 : coverage?.coverage_percent ?? null;
}

/** The coverage pill of a whole Run (or of a result view). */
export function coveragePill(coverage: ResultCoverage | null | undefined, options: { withheld?: boolean } = {}): CoveragePill {
  const title = coverageReasonText(coverage);
  if (options.withheld) return { tone: "caution", text: valueStateText("withheld"), title };
  if (!coverage) return { tone: "muted", text: tr("coverage.notRecorded"), title };
  switch (coverage.annual_status) {
    case "complete": return { tone: "ok", text: tr("coverage.complete"), title };
    case "non_annual": return { tone: "caution", text: valueStateText("non_annual"), title };
    case "in_progress": return { tone: "info", text: valueStateText("in_progress"), title };
    case "invalid": return { tone: "danger", text: valueStateText("invalid"), title };
    default: return { tone: "caution", text: valueStateText(isStoppedCoverage(coverage) ? "stopped" : "partial_year", coverage.coverage_percent), title };
  }
}

/** The pill of one year: a recorded complete year is "Complete year" even inside a stopped Run. */
export function yearCoveragePill(coverage: ResultCoverage | null | undefined, year: number): CoveragePill {
  if (!coverage) return coveragePill(coverage);
  if (coverage.annual_status === "non_annual" || coverage.annual_status === "invalid") return coveragePill(coverage);
  const row = coverage.years?.find((item) => item.year === year);
  if (row?.complete) return { tone: "ok", text: tr("coverage.complete"), title: COVERAGE_REASON_TEXT.annual_coverage_complete };
  if (coverage.annual_status === "in_progress") return { tone: "info", text: valueStateText("in_progress"), title: coverageReasonText(coverage) };
  const key = isStoppedCoverage(coverage) ? "stopped" : "partial_year";
  return { tone: "caution", text: valueStateText(key, row ? row.coverage_fraction * 100 : null), title: coverageReasonText(coverage) };
}

/** Annual totals are published only for a complete verdict. Without a verdict (older backend) they stay visible under "Coverage not recorded". */
export function annualTotalsPublishable(coverage: ResultCoverage | null | undefined): boolean {
  return !coverage || coverage.annual_status === "complete";
}

export function yearTotalsPublishable(coverage: ResultCoverage | null | undefined, year: number): boolean {
  if (!coverage) return true;
  if (coverage.annual_status === "non_annual" || coverage.annual_status === "invalid") return false;
  return Boolean(coverage.years?.find((item) => item.year === year)?.complete);
}

/**
 * Spec 4.4: the empty-list sentence may claim a whole year only when the year is complete.
 * R-D3 (round R1-5): a non-annual Run (smoke, one-day lesson) is not "0% of the
 * year"; it names the periods it computed when the caller knows them.
 */
export function reliabilityEmptyText(coverage: ResultCoverage | null | undefined, year: number, computedPeriods?: number | null): string {
  const row = coverage?.years?.find((item) => item.year === year);
  if (coverage?.annual_status === "non_annual") {
    const periods = row?.period_count ?? computedPeriods;
    const count = periods ? formatNumber(periods, 0) : null;
    return count ? tr("coverage.empty.nonAnnualPeriods", { periods: count, year }) : tr("coverage.empty.nonAnnual", { year });
  }
  if (row?.complete) return tr("coverage.empty.complete", { year });
  const percent = row ? row.coverage_fraction * 100 : coverage?.coverage_percent ?? null;
  const shown = formatNumber(percent, 1);
  if (shown == null) return tr("coverage.empty.unknown", { year });
  return tr("coverage.empty.partial", { percent: shown, year });
}
