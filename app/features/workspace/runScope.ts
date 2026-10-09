import type { RunMode } from "../runs/types";
import { en } from "../../i18n/en.ts";
import { localizedTable, tr } from "../../i18n/index.ts";

type ScopeStudy = { extensions?: { value_101?: unknown; frozen_recovery?: { required_mode?: string } }; selected_extensions?: readonly string[]; start_year?: number | string; end_year?: number | string };
type ScopePack = { allowed_run_modes?: RunMode[]; teaching_only?: boolean };
// P1 W5: the scope names are dictionary messages (scope.*) in the interface language.
export const RUN_SCOPE_LABELS: Readonly<Record<RunMode, string>> = localizedTable<RunMode>({
  smoke: "scope.smoke", two_year_smoke: "scope.two_year_smoke",
  validation_24h: "scope.validation_24h", validation_168h: "scope.validation_168h",
  value_101_day: "scope.value_101_day", two_year: "scope.two_year", full: "scope.full",
});
export const ALL_RUN_MODES = Object.keys(RUN_SCOPE_LABELS) as RunMode[];
/** Scopes that need at least two configured years (gridform_core/run_policy.py maximum_years = 2). */
export const TWO_YEAR_RUN_MODES: readonly RunMode[] = ["two_year_smoke", "two_year"];

/** R5-3 低2: a one-year Study is not offered a scope that readiness refuses. */
function coversTwoYears(project: ScopeStudy | undefined): boolean {
  const start = Number(project?.start_year), end = Number(project?.end_year);
  return !Number.isFinite(start) || !Number.isFinite(end) || end > start;
}
/** F-D2 (spec 11.5): scopes that run the market step only, never extension hooks
 * (mirrors gridform_core/run_policy.py PSM_ONLY_RUN_MODES). */
export const PSM_ONLY_RUN_MODES: readonly RunMode[] = ["value_101_day"];
export const EXTENSIONS_DO_NOT_RUN_NOTE = en["scope.extensionsDoNotRun"];

/** Scope option text; a market-step-only scope is annotated when the Study selects extensions. */
export function runScopeOptionLabel(mode: RunMode, project?: ScopeStudy): string {
  const skipsSelected = PSM_ONLY_RUN_MODES.includes(mode) && Boolean(project?.selected_extensions?.length);
  return skipsSelected ? tr("scope.optionWithNote", { scope: RUN_SCOPE_LABELS[mode] }) : RUN_SCOPE_LABELS[mode];
}

/** The UI options, readiness and launch share this exact eligibility policy. */
export function runModesForStudy(project: ScopeStudy | undefined, pack?: ScopePack): RunMode[] {
  const recovery = project?.extensions?.frozen_recovery;
  const required = recovery?.required_mode;
  const allowed = pack?.allowed_run_modes ?? (pack?.teaching_only ? [] : ALL_RUN_MODES.filter(mode => Boolean(required) || !["validation_24h", "validation_168h"].includes(mode)));
  return allowed.filter(mode => (!required || mode === required)
    && (mode !== "value_101_day" || Boolean(project?.extensions?.value_101) || Boolean(recovery))
    && (Boolean(required) || !TWO_YEAR_RUN_MODES.includes(mode) || coversTwoYears(project)));
}

export function selectedRunScope(requested: RunMode, eligible: RunMode[]): RunMode | null {
  return eligible.includes(requested) ? requested : eligible.includes("smoke") ? "smoke" : eligible[0] ?? null;
}
