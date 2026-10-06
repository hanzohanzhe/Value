// Full-year A2 stress events of a Run (spec 4.4; decision A2; P0-9 M7).
// Pure view logic: the rows come from GET /api/runs/<id>/market/stress-events
// (gridform_core/market_replay.query_stress_events); nothing here derives a
// shortfall, it only formats what the ledger recorded.
import { formatEnergy } from "../shared/format.ts";
import { reliabilityEmptyText, type ResultCoverage } from "../shared/coverageView.ts";
import { RELIABILITY_PAGE_SIZE, modelTimestamp, replayWindowStart } from "../network/reliabilityView.ts";

export const STRESS_EVENT_TYPE = "stress (supply < demand)";

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
    type: STRESS_EVENT_TYPE,
    replayFrom: replayWindowStart(event.start_period),
  };
}

/** One page of the whole year's events: no period window (F3-07, spec 4.4). */
export function stressEventQuery(year: number, offset: number): URLSearchParams {
  return new URLSearchParams({ year: String(year), limit: String(RELIABILITY_PAGE_SIZE), offset: String(offset) });
}

/** Spec 4.4: what an empty list says. "No stress events recorded in {year}." only for a complete year. */
export function stressEventEmptyText(page: Pick<StressEventPage, "status">, coverage: ResultCoverage | null | undefined, year: number): string {
  if (page.status !== "recorded") return "This Run's ledger does not record stress events (it predates the A2 stress accounting).";
  return reliabilityEmptyText(coverage, year);
}
