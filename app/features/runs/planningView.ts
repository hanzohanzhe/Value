// Planning evidence on the Runs page and in Inspect (R4, four-role report R-中1, R-低1).
// The server answers /planning/summary with years[] (gridform_core/planning_index
// .planning_summary_payload); a response without it is shown as "not recorded",
// never as a JavaScript error.
import type { PlanningYear } from "./types";
import { en } from "../../i18n/en.ts";
import { tr } from "../../i18n/index.ts";

/** English text of the message "planning.yearNotRecorded" (the page shows it in the interface language). */
export const PLANNING_YEAR_NOT_RECORDED = en["planning.yearNotRecorded"];

/** The summary of one year, or a sentence saying why there is none. */
export function planningYearFromPayload(payload: unknown, year: number): { summary: PlanningYear | null; error: string } {
  const years = payload && typeof payload === "object" ? (payload as { years?: unknown }).years : undefined;
  if (!Array.isArray(years)) return { summary: null, error: tr("planning.yearNotRecorded") };
  const summary = years.find((item): item is PlanningYear => Boolean(item) && typeof item === "object" && (item as PlanningYear).year === year) ?? null;
  return { summary, error: summary ? "" : tr("planning.yearNotRecorded") };
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
  return tr(planningRowsPerYear(page) ? "planning.projectYearRecords" : "planning.durableRecords", { count: page.total });
}

/** English text of the message "planning.projectYearNote" (Inspect shows planningProjectYearNote()). */
export const PLANNING_PROJECT_YEAR_NOTE = en["planning.projectYearNote"];
export function planningProjectYearNote(): string {
  return tr("planning.projectYearNote");
}
