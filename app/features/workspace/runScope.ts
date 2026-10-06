import type { RunMode } from "../runs/types";

type ScopeStudy = { extensions?: { value_101?: unknown; frozen_recovery?: { required_mode?: string } }; selected_extensions?: readonly string[] };
type ScopePack = { allowed_run_modes?: RunMode[]; teaching_only?: boolean };
export const RUN_SCOPE_LABELS: Record<RunMode, string> = {
  smoke: "Two-period wiring check", two_year_smoke: "Two-year hand-off check",
  validation_24h: "24-hour validation scope", validation_168h: "168-hour validation scope",
  value_101_day: "One-day market lesson", two_year: "Two full model years", full: "Complete study",
};
export const ALL_RUN_MODES = Object.keys(RUN_SCOPE_LABELS) as RunMode[];
/** F-D2 (spec 11.5): scopes that run the market step only, never extension hooks
 * (mirrors gridform_core/run_policy.py PSM_ONLY_RUN_MODES). */
export const PSM_ONLY_RUN_MODES: readonly RunMode[] = ["value_101_day"];
export const EXTENSIONS_DO_NOT_RUN_NOTE = "(extensions do not run)";

/** Scope option text; a market-step-only scope is annotated when the Study selects extensions. */
export function runScopeOptionLabel(mode: RunMode, project?: ScopeStudy): string {
  const skipsSelected = PSM_ONLY_RUN_MODES.includes(mode) && Boolean(project?.selected_extensions?.length);
  return skipsSelected ? `${RUN_SCOPE_LABELS[mode]} ${EXTENSIONS_DO_NOT_RUN_NOTE}` : RUN_SCOPE_LABELS[mode];
}

/** The UI options, readiness and launch share this exact eligibility policy. */
export function runModesForStudy(project: ScopeStudy | undefined, pack?: ScopePack): RunMode[] {
  const recovery = project?.extensions?.frozen_recovery;
  const required = recovery?.required_mode;
  const allowed = pack?.allowed_run_modes ?? (pack?.teaching_only ? [] : ALL_RUN_MODES.filter(mode => Boolean(required) || !["validation_24h", "validation_168h"].includes(mode)));
  return allowed.filter(mode => (!required || mode === required)
    && (mode !== "value_101_day" || Boolean(project?.extensions?.value_101) || Boolean(recovery)));
}

export function selectedRunScope(requested: RunMode, eligible: RunMode[]): RunMode | null {
  return eligible.includes(requested) ? requested : eligible.includes("smoke") ? "smoke" : eligible[0] ?? null;
}
