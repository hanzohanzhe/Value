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

/**
 * R4 R-低1: the Inspect planning table title. The project index has one row
 * per project and model year (record_unit "project_year"), so a project shows
 * once per year; a legacy planning ledger has one durable row per project.
 */
type PlanningPage = { total: number; record_unit?: string | null; items: { year?: number | null }[] };

export function planningRowsPerYear(page: PlanningPage): boolean {
  return page.record_unit === "project_year" || page.items.some((item) => typeof item.year === "number");
}

export function planningRecordsTitle(page: PlanningPage): string {
  return planningRowsPerYear(page) ? `${page.total} project-year records` : `${page.total} durable project records`;
}

export const PLANNING_PROJECT_YEAR_NOTE = "One row per project and model year: a project appears once for each year it is in the pipeline, with that year's status.";
