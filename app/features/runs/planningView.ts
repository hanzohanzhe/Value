// Planning evidence on the Runs page and in Inspect (R4, four-role report R-中1, R-低1).
// The server answers /planning/summary with years[] (gridform_core/planning_index
// .planning_summary_payload); a response without it is shown as "not recorded",
// never as a JavaScript error.
import type { PlanningYear } from "./types";

export const PLANNING_YEAR_NOT_RECORDED = "Planning evidence is not recorded for this year.";

/** The summary of one year, or a sentence saying why there is none. */
export function planningYearFromPayload(payload: unknown, year: number): { summary: PlanningYear | null; error: string } {
  const years = payload && typeof payload === "object" ? (payload as { years?: unknown }).years : undefined;
  if (!Array.isArray(years)) return { summary: null, error: PLANNING_YEAR_NOT_RECORDED };
  const summary = years.find((item): item is PlanningYear => Boolean(item) && typeof item === "object" && (item as PlanningYear).year === year) ?? null;
  return { summary, error: summary ? "" : PLANNING_YEAR_NOT_RECORDED };
}
