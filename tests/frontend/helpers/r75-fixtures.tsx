// Test-only wrapper (R7-5): the solver state word and its reason, rendered in
// the interface language, from the same solverDisplay the Network page uses.
import { LocaleProvider } from "../../../app/i18n/LocaleProvider";
import type { Locale } from "../../../app/i18n/index.ts";
import { DEFAULT_ZONAL_SOLVER_CONTRACT, type SolverValidationSummary } from "../../../app/features/network/networkRedispatch";
import { SolverEvidenceReason, SolverEvidenceState, solverDisplay } from "../../../app/features/network/NetworkRedispatchView";

export function SolverEvidenceIn({ locale, summary }: { locale: Locale; summary: SolverValidationSummary }) {
  const display = solverDisplay({ id: "run-1", status: "completed" }, "success", DEFAULT_ZONAL_SOLVER_CONTRACT, "valid", summary);
  return <LocaleProvider initialLocale={locale}>
    <SolverEvidenceState display={display} />
    <SolverEvidenceReason display={display} />
  </LocaleProvider>;
}
