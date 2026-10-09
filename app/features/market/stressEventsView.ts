// Full-year A2 stress events of a Run (spec 4.4; decision A2; P0-9 M7).
// Pure view logic: the rows come from GET /api/runs/<id>/market/stress-events
// (gridform_core/market_replay.query_stress_events); nothing here derives a
// shortfall, it only formats what the ledger recorded.
import { formatEnergy } from "../shared/format.ts";
import { reliabilityEmptyText, type ResultCoverage } from "../shared/coverageView.ts";
import { RELIABILITY_PAGE_SIZE, modelTimestamp, replayWindowStart } from "../network/reliabilityView.ts";
import { en } from "../../i18n/en.ts";
import { tr } from "../../i18n/index.ts";

/** English text of the message "stressView.type" (rows carry it in the interface language). */
export const STRESS_EVENT_TYPE = en["stressView.type"];

export type StressEvent = {
  year: number; event_index: number; start_period: number; last_period: number; periods: number;
  start_timestamp?: string; shortfall_mwh: number | null; recorded_unserved_mwh?: number | null;
  hidden_unserved_mwh?: number | null; boundary_id?: string; event_type?: string;
};

export type StressEventPage = {
  schema_version?: string; status: "recorded" | "not_recorded" | string; year: number | null;
  items: StressEvent[]; total: number; limit: number; offset: number; has_more: boolean;
  stress_periods?: number; shortfall_mwh?: number; timezone?: string; period_hours?: number;
};

export type StressEventRow = { key: string; start: string; startPeriod: number; periods: number; shortfall: string | null; type: string; replayFrom: number };

export function stressEventRow(event: StressEvent, periodHours = 0.5): StressEventRow {
  return {
    key: `${event.year}-${event.event_index}`,
    start: modelTimestamp(event.year, event.start_period, periodHours),
    startPeriod: event.start_period,
    periods: event.periods,
    shortfall: formatEnergy(event.shortfall_mwh),
    type: tr("stressView.type"),
    replayFrom: replayWindowStart(event.start_period),
  };
}

/** A response is a stress-event page only with a status, an item array and integer paging fields. */
export function isStressEventPage(value: unknown): value is StressEventPage {
  if (!value || typeof value !== "object") return false;
  const page = value as Partial<StressEventPage>;
  return typeof page.status === "string" && Array.isArray(page.items) && Number.isInteger(page.total) && Number.isInteger(page.limit) && Number.isInteger(page.offset);
}

/** One page of the whole year's events: no period window (F3-07, spec 4.4). */
export function stressEventQuery(year: number, offset: number): URLSearchParams {
  return new URLSearchParams({ year: String(year), limit: String(RELIABILITY_PAGE_SIZE), offset: String(offset) });
}

/** Spec 4.4: what an empty list says. "No stress events recorded in {year}." only for a complete year. */
export function stressEventEmptyText(page: Pick<StressEventPage, "status">, coverage: ResultCoverage | null | undefined, year: number, computedPeriods?: number | null): string {
  if (page.status !== "recorded") return tr("stressView.notRecorded");
  return reliabilityEmptyText(coverage, year, computedPeriods);
}

/** R-D3: the list heading claims a full year only for an annual Run. */
export function stressEventHeading(coverage: ResultCoverage | null | undefined, year: number): string {
  return tr(coverage?.annual_status === "non_annual" ? "stressView.headingNonAnnual" : "stressView.heading", { year });
}

/** R-D3: the heading summary; a recorded ledger without events says "None" (spec 2.3), not "—". */
export function stressEventSummary(page: Pick<StressEventPage, "status" | "total" | "stress_periods" | "shortfall_mwh"> | undefined): string {
  if (page?.status !== "recorded") return "—";
  if (page.total === 0) return tr("stressView.none");
  return tr("stressView.summary", { count: page.total, periods: page.stress_periods ?? "—", shortfall: formatEnergy(page.shortfall_mwh) ?? "—" });
}
