import type { RunMode } from "../runs/types";

type ScopeStudy = { extensions?: { value_101?: unknown; frozen_recovery?: { required_mode?: string } } };
type ScopePack = { allowed_run_modes?: RunMode[]; teaching_only?: boolean };
export const RUN_SCOPE_LABELS: Record<RunMode, string> = {
  smoke: "Two-period wiring check", two_year_smoke: "Two-year hand-off check",
  validation_24h: "24-hour validation scope", validation_168h: "168-hour validation scope",
  value_101_day: "One-day market lesson", two_year: "Two full model years", full: "Complete study",
};
export const ALL_RUN_MODES = Object.keys(RUN_SCOPE_LABELS) as RunMode[];

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
