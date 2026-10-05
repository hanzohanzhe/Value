// Annual-coverage presentation (spec 4.2 / 4.4 / 4.6; P0-9 S5/S6).
// The verdict comes from the backend (gridform_core/result_coverage.py); this
// module only turns it into a pill, a sentence and the publish/withhold rule.
import { formatNumber, withUnit } from "./format.ts";
import { valueStateText } from "./valueStates.ts";
import type { PillTone } from "./Callout.tsx";

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
export const COVERAGE_REASON_TEXT: Readonly<Record<string, string>> = {
  annual_evidence_withheld_for_nonannual_run: "This Run's scope clears fewer than 17,520 periods a year, so its totals are not annual results.",
  run_in_progress: "The Run has not finished; totals cover only the periods computed so far.",
  run_cancelled_before_full_coverage: "The Run was cancelled before it covered its years; totals cover only the computed periods.",
  run_failed_before_full_coverage: "The Run stopped with a failure before it covered its years; totals cover only the computed periods.",
  annual_year_set_mismatch: "The years recorded in the ledger differ from the years the Run declared.",
  annual_period_boundary_incomplete: "At least one year does not cover periods 0 to 17,519 exactly once.",
  annual_coverage_complete: "Every declared year covers all 17,520 periods.",
};

export function isResultCoverage(value: unknown): value is ResultCoverage {
  return typeof value === "object" && value !== null
    && ["complete", "partial", "non_annual", "in_progress", "invalid"].includes(String((value as ResultCoverage).annual_status));
}

export function coverageReasonText(coverage: ResultCoverage | null | undefined): string {
  if (!coverage) return "This Run does not record its annual coverage.";
  return COVERAGE_REASON_TEXT[coverage.reason_code] ?? coverage.reason_code.replaceAll("_", " ");
}

/** The coverage pill of a whole Run (or of a result view). */
export function coveragePill(coverage: ResultCoverage | null | undefined, options: { withheld?: boolean } = {}): CoveragePill {
  const title = coverageReasonText(coverage);
  if (options.withheld) return { tone: "caution", text: valueStateText("withheld"), title };
  if (!coverage) return { tone: "muted", text: "Coverage not recorded", title };
  switch (coverage.annual_status) {
    case "complete": return { tone: "ok", text: "Complete year", title };
    case "non_annual": return { tone: "caution", text: valueStateText("non_annual"), title };
    case "in_progress": return { tone: "info", text: valueStateText("in_progress"), title };
    case "invalid": return { tone: "danger", text: valueStateText("invalid"), title };
    default: return { tone: "caution", text: valueStateText("partial_year", coverage.coverage_percent), title };
  }
}

/** The pill of one year: a recorded complete year is "Complete year" even inside a stopped Run. */
export function yearCoveragePill(coverage: ResultCoverage | null | undefined, year: number): CoveragePill {
  if (!coverage) return coveragePill(coverage);
  if (coverage.annual_status === "non_annual" || coverage.annual_status === "invalid") return coveragePill(coverage);
  const row = coverage.years?.find((item) => item.year === year);
  if (row?.complete) return { tone: "ok", text: "Complete year", title: COVERAGE_REASON_TEXT.annual_coverage_complete };
  return { tone: "caution", text: valueStateText("partial_year", row ? row.coverage_fraction * 100 : null), title: coverageReasonText(coverage) };
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

/** Spec 4.4: the empty-list sentence may claim a whole year only when the year is complete. */
export function reliabilityEmptyText(coverage: ResultCoverage | null | undefined, year: number): string {
  const row = coverage?.years?.find((item) => item.year === year);
  if (row?.complete && coverage?.annual_status !== "non_annual") return `No stress events recorded in ${year}.`;
  const percent = row ? row.coverage_fraction * 100 : coverage?.coverage_percent ?? null;
  if (percent == null) return `No stress events recorded in the computed periods of ${year}; this Run does not record its coverage.`;
  return `No stress events in the ${withUnit(formatNumber(percent, 1), "%", "")} of ${year} that has been computed.`;
}
