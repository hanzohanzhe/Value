// Methodology profile and validation presentation of one Run (spec 2.2, 2.3;
// plan X0 S12, P0-9 S11). The backend decides every status
// (gridform_core/result_advisories.present_scientific_status); this module only
// turns the recorded fields into a pill, two status-bar fields and the
// prioritised notices. A missing field is "not recorded", never a pass.
import { formatEnergy, formatNumber } from "../shared/format.ts";
import type { PillTone } from "../shared/Callout.tsx";

/** Machine id of the frozen doctoral profile (DECISIONS Q2). */
export const DOCTORAL_PROFILE_ID = "doctoral-lineage-0.6.0a2";
/** The corrected default profile ("value-corrected", possibly versioned as value-corrected-*). */
export const CORRECTED_PROFILE_PREFIX = "value-corrected";

export const DOCTORAL_PROFILE_LABEL = "Doctoral reproduction (as implemented in VALUE 0.6.0-alpha.2)";
export const CORRECTED_PROFILE_LABEL = "Corrected methodology (default)";

export type MethodologyRecord = {
  status?: "recorded" | "not_recorded" | "unresolved" | string;
  profile_id?: string | null;
  profile_version?: string;
  label?: string;
  note?: string;
  catalogue_sha256?: string;
  profile_definition_sha256?: string;
  applied_corrections_sha256?: string;
  error?: unknown;
};

export type EnergyBalanceRecord = {
  status?: string;
  enforcement?: string;
  envelope_lower_violations?: number | null;
  envelope_upper_violations?: number | null;
  maximum_envelope_violation_mwh?: number | null;
  [key: string]: unknown;
};

export type StressRecord = {
  stress_periods?: number | null;
  shortfall_mwh?: number | null;
  shortfall_basis?: string | null;
  event_count?: number | null;
  [key: string]: unknown;
};

export type RunAdvisory = {
  id: string;
  severity?: string;
  title?: string;
  summary?: string;
  affected_metrics?: string[];
};

export type ResultPublication = {
  status?: "published" | "withheld" | string;
  rule?: string;
  reason_code?: string;
  raw_invariants_status?: string;
  message?: string;
  available_in?: string[];
};

/** The validation fields of a Run detail or listing row (both are optional: older backends send none). */
export type RunValidationFields = {
  methodology?: MethodologyRecord | null;
  energy_balance_status?: string | null;
  energy_balance?: EnergyBalanceRecord | null;
  stress?: StressRecord | null;
  advisories?: RunAdvisory[] | null;
  advisory_summary?: { count?: number; max_severity?: string | null; needs_review?: boolean } | null;
  result_publication?: ResultPublication | null;
  contract_validation_status?: string | null;
  scientific_validation_status?: string | null;
  scientific_scenario_status?: string | null;
  recorded_scientific_validation_status?: string | null;
  recorded_validation_statuses?: Record<string, string> | null;
};

export type ProfileKind = "corrected" | "doctoral" | "pre_profile" | "unresolved" | "unreported" | "other";
export type ProfileBadge = { kind: ProfileKind; tone: PillTone; text: string; title: string; profileId?: string };

function text(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}

function count(value: unknown): number | undefined {
  return typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : undefined;
}

function finite(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

export function profileKind(methodology: MethodologyRecord | null | undefined): ProfileKind {
  if (!methodology || typeof methodology !== "object") return "unreported";
  const id = text(methodology.profile_id);
  if (methodology.status === "not_recorded") return "pre_profile";
  if (methodology.status === "unresolved") return "unresolved";
  if (!id) return "unreported";
  if (id === DOCTORAL_PROFILE_ID) return "doctoral";
  if (id === CORRECTED_PROFILE_PREFIX || id.startsWith(`${CORRECTED_PROFILE_PREFIX}-`)) return "corrected";
  return "other";
}

/** Spec 2.2: the methodology pill of a Run. */
export function profileBadge(methodology: MethodologyRecord | null | undefined): ProfileBadge {
  const kind = profileKind(methodology);
  const profileId = text(methodology?.profile_id);
  switch (kind) {
    case "corrected":
      return { kind, profileId, tone: "info", text: CORRECTED_PROFILE_LABEL, title: `Current default methodology with review fixes of 2026-10. Profile ${profileId}.` };
    case "doctoral":
      return {
        kind, profileId, tone: "caution", text: DOCTORAL_PROFILE_LABEL,
        title: "Reproduces the thesis behaviour as implemented in VALUE 0.6.0-alpha.2, including declared deviations. Not an exact reproduction of the 2026-07-18 retained trajectory.",
      };
    case "pre_profile":
      return { kind, tone: "muted", text: "Methodology not recorded (pre-2026-10 run)", title: "This Run was produced before methodology profiles existed. See advisories." };
    case "unresolved":
      // Recorded after profiles existed, but the id is not in this catalogue: not a pre-fix Run.
      return { kind, tone: "muted", text: "Methodology not recorded", title: "This Run names a methodology profile this version of VALUE cannot resolve." };
    case "other":
      return { kind, profileId, tone: "muted", text: text(methodology?.label) ?? `Methodology ${profileId}`, title: `Profile ${profileId}.` };
    default:
      // Older backend: no methodology field at all. Degrade, do not guess (principle 3).
      return { kind, tone: "muted", text: "Methodology not recorded", title: "The model service did not report a methodology for this Run." };
  }
}

export type CheckField = { tone: "ok" | "danger" | "caution" | "muted"; text: string; dot: boolean; title?: string };

const REPORT_ONLY_TITLE = "Residuals are reported, not yet enforced";

/** Spec 2.3: the Energy balance status-bar field. */
export function energyBalanceField(status: unknown, enforcement?: unknown): CheckField {
  const reportOnly = typeof enforcement === "string" && enforcement.startsWith("report_only") ? REPORT_ONLY_TITLE : undefined;
  switch (status) {
    case "passed": return { tone: "ok", text: "Passed", dot: true, title: reportOnly };
    case "failed": return { tone: "danger", text: "Failed", dot: true, title: reportOnly };
    case "report_only": return { tone: "caution", text: "Reported", dot: true, title: REPORT_ONLY_TITLE };
    case "reproduction_with_declared_deviations": return { tone: "caution", text: "Declared deviations", dot: true, title: reportOnly };
    case "superseded_pre_fix": return { tone: "caution", text: "Superseded", dot: true, title: "Produced before the 2026-10 review fixes." };
    case "not_evaluated": return { tone: "muted", text: "Not evaluated", dot: false, title: reportOnly };
    case undefined: case null: case "": return { tone: "muted", text: "Not recorded", dot: false };
    default: return { tone: "muted", text: String(status).replaceAll("_", " "), dot: false };
  }
}

/** The new validation vocabulary on the existing Contract check / Scientific validation fields; other values keep the plain label. */
export function legacyStatusField(status: string, recorded?: string | null): CheckField | null {
  if (status === "superseded_pre_fix") {
    const original = text(recorded);
    return {
      tone: "caution", text: "Superseded", dot: true,
      title: original ? `Recorded as "${original.replaceAll("_", " ")}" by a version produced before the 2026-10 review fixes.` : "Produced before the 2026-10 review fixes.",
    };
  }
  if (status === "reproduction_with_declared_deviations") return { tone: "caution", text: "Declared deviations", dot: true };
  return null;
}

function periods(n: number): string {
  return `${formatNumber(n, 0)} ${n === 1 ? "period" : "periods"}`;
}

/** Spec 2.3: the Stress events status-bar field (A2). None is muted, never green. */
export function stressField(stress: StressRecord | null | undefined): CheckField {
  const stressPeriods = count(stress?.stress_periods);
  if (stressPeriods === undefined) return { tone: "muted", text: "Not recorded", dot: false };
  if (stressPeriods === 0) return { tone: "muted", text: "None", dot: false, title: "No period in which accepted supply fell short of demand. This is not a validation result." };
  const shortfall = formatEnergy(finite(stress?.shortfall_mwh));
  const lowerBound = stress?.shortfall_basis === "lower_bound";
  return {
    tone: "caution", dot: true,
    text: shortfall ? `${periods(stressPeriods)} · ${shortfall}` : periods(stressPeriods),
    title: shortfall
      ? lowerBound ? "Shortfall is the demand that accepted supply did not meet (a lower bound: surplus routing was not recorded)." : "Shortfall recorded as unserved energy."
      : "The shortfall energy was not recorded.",
  };
}

export type NoticeId = "energy_balance_failed" | "results_withheld" | "pre_fix" | "stress_events";
export type NoticeAction = "open_residuals" | "open_inspect" | "export_ledger" | "view_advisories" | "show_stress_events";
export type RunNotice = {
  id: NoticeId;
  tone: "danger" | "caution";
  title: string;
  body: string;
  actions: NoticeAction[];
  advisoryCount?: number;
};

const ORIGINAL_FIELDS = ["scientific_validation_status", "scientific_scenario_status", "contract_validation_status"];

function supersededFields(run: RunValidationFields): boolean {
  return ORIGINAL_FIELDS.some((field) => (run as Record<string, unknown>)[field] === "superseded_pre_fix");
}

/** The validation status the Run originally recorded (shown when it is superseded). */
export function originalValidationStatus(run: RunValidationFields): string {
  const recorded = run.recorded_validation_statuses && typeof run.recorded_validation_statuses === "object" ? run.recorded_validation_statuses : {};
  const value = text(run.recorded_scientific_validation_status)
    ?? ORIGINAL_FIELDS.map((field) => text(recorded[field])).find(Boolean)
    ?? (supersededFields(run) ? undefined : text(run.scientific_validation_status));
  return value ? value.replaceAll("_", " ") : "not recorded";
}

function residualSentence(balance: EnergyBalanceRecord | null | undefined): string {
  const lower = count(balance?.envelope_lower_violations);
  const upper = count(balance?.envelope_upper_violations);
  const failing = lower === undefined && upper === undefined ? undefined : (lower ?? 0) + (upper ?? 0);
  const largest = formatEnergy(finite(balance?.maximum_envelope_violation_mwh));
  const where = failing ? `${periods(failing)} where` : "periods where";
  const residual = failing && largest ? ` (largest residual ${largest})` : "";
  return `The independent ledger check found ${where} supply and use do not reconcile${residual}. Treat results from this Run as unverified.`;
}

/** Spec 2.3: every notice that applies, most important first. The bar shows the first one. */
export function runNotices(run: RunValidationFields | null | undefined): RunNotice[] {
  if (!run) return [];
  const kind = profileKind(run.methodology);
  const notices: RunNotice[] = [];
  // 1. A failed independent check. The doctoral profile's failure is notice 2 (withheld), not a defect.
  if (run.energy_balance_status === "failed" && kind !== "doctoral") {
    notices.push({ id: "energy_balance_failed", tone: "danger", title: "Energy balance check failed", body: residualSentence(run.energy_balance), actions: ["open_residuals"] });
  }
  // 2. Q14: annual results of a reproduction Run that did not pass its raw invariants.
  if (run.result_publication?.status === "withheld") {
    notices.push({
      id: "results_withheld", tone: "caution", title: "Annual results withheld for this reproduction run",
      body: "Doctoral reproduction runs keep the thesis behaviour, including declared deviations, so they do not pass the physical energy-balance check. Annual results are therefore not published on result pages. The full ledger remains available.",
      actions: ["open_inspect", "export_ledger"],
    });
  }
  // 3. A Run produced before the review fixes (no profile, or a superseded positive claim).
  if (kind === "pre_profile" || supersededFields(run)) {
    const advisoryCount = Array.isArray(run.advisories) ? run.advisories.length : count(run.advisory_summary?.count) ?? 0;
    notices.push({
      id: "pre_fix", tone: "caution", title: "Produced before the 2026-10 review fixes",
      body: `This Run's original validation status was "${originalValidationStatus(run)}". It was produced by a version with known issues; see the advisories that apply to it.`,
      actions: ["view_advisories"], advisoryCount,
    });
  }
  // 4. A2 stress events: recorded, never blocking.
  const stressPeriods = count(run.stress?.stress_periods);
  if (stressPeriods !== undefined && stressPeriods > 0) {
    const shortfall = formatEnergy(finite(run.stress?.shortfall_mwh));
    notices.push({
      id: "stress_events", tone: "caution", title: `Supply fell short of demand in ${periods(stressPeriods)}`,
      body: `${shortfall ? `Total shortfall ${shortfall}. ` : ""}These are stress events: demand exceeded accepted supply. Dispatch was not altered; the shortfall is recorded as unserved energy.`,
      actions: ["show_stress_events"],
    });
  }
  return notices;
}

export const NOTICE_ACTION_LABELS: Readonly<Record<NoticeAction, string>> = {
  open_residuals: "Open residuals in Inspect",
  open_inspect: "Open in Inspect",
  export_ledger: "Export ledger",
  view_advisories: "View advisories",
  show_stress_events: "Show stress events",
};

/** The advisories of a Run detail; the listing row carries only the count. */
export function runAdvisories(run: RunValidationFields | null | undefined): RunAdvisory[] {
  return Array.isArray(run?.advisories) ? run.advisories.filter((item): item is RunAdvisory => Boolean(item && typeof item === "object" && text(item.id))) : [];
}
