// Full-year stress / lost-load list (spec 4.4; P0-9 S6, F3-07). Pure view logic.
import { formatEnergy } from "../shared/format.ts";
import { modelTimestamp } from "../shared/modelClock.ts";
import { tr } from "../../i18n/index.ts";

/** S-中1: the model clock (UTC, fixed 365-day year) lives in shared/modelClock.ts. */
export { modelTimestamp };

export const RELIABILITY_PAGE_SIZE = 50;
/** A Replay jump opens Market replay a few periods before the event starts. */
export const REPLAY_LEAD_PERIODS = 4;

export type ReliabilityEvent = {
  event_id: string; year: number; start_period: number; end_period: number;
  observed_half_hours?: number; event_duration_hours?: number; unserved_mwh?: number | null;
  affected_zones_json?: string;
};

export type ReliabilityRow = {
  key: string; start: string; startPeriod: number; periods: number; shortfall: string | null; type: string; zones: string;
};

function zones(raw: string | undefined): string {
  if (!raw) return "—";
  try {
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) && parsed.length ? parsed.map(String).join(", ") : "—";
  } catch {
    return raw;
  }
}

export function reliabilityRow(event: ReliabilityEvent, periodHours = 0.5): ReliabilityRow {
  const periods = event.observed_half_hours ?? (event.end_period - event.start_period + 1);
  return {
    key: event.event_id,
    start: modelTimestamp(event.year, event.start_period, periodHours),
    startPeriod: event.start_period,
    periods,
    shortfall: formatEnergy(event.unserved_mwh),
    type: tr("reliabilityView.type"),
    zones: zones(event.affected_zones_json),
  };
}

export function replayWindowStart(startPeriod: number): number {
  return Math.max(0, startPeriod - REPLAY_LEAD_PERIODS);
}

/** Query of one page of the whole year's events: no period window (F3-07). */
export function reliabilityQuery(year: number, offset: number): URLSearchParams {
  return new URLSearchParams({ year: String(year), limit: String(RELIABILITY_PAGE_SIZE), offset: String(offset) });
}
