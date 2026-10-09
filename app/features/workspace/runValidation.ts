// Methodology profile and validation presentation of one Run (spec 2.2, 2.3;
// plan X0 S12, P0-9 S11). The backend decides every status
// (gridform_core/result_advisories.present_scientific_status); this module only
// turns the recorded fields into a pill, two status-bar fields and the
// prioritised notices. A missing field is "not recorded", never a pass.
import { formatEnergy, formatNumber, withUnit } from "../shared/format.ts";
import type { PillTone } from "../shared/Callout.tsx";
import { en } from "../../i18n/en.ts";
import { localizedTable, tr } from "../../i18n/index.ts";

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
  /** A2 account (P0-4 S7): the gate's open periods and largest closing residual. */
  balance_account?: { boundary_id?: string | null; open_periods?: number | null; unexplained_open_periods?: number | null; max_abs_closing_residual_mwh?: number | null } | null;
  /** The raw boundary verdict, kept as evidence (F-P04-5: shown only in Inspect). */
  raw_boundary_status?: string | null;
  boundary_id?: string | null;
  periods?: number | null;
  maximum_absolute_boundary_residual_mwh?: number | null;
  maximum_absolute_raw_residual_mwh?: number | null;
  [key: string]: unknown;
};

/** P0-4 S7: the three validation gates of a Run. */
export type ValidationGateRecord = {
  policy?: string;
  profile_id?: string | null;
  status?: string;
  gates?: Partial<Record<GateName, string>> | null;
};

/** P0-4 S7 / model_runner: why annual results were not published (production policy). */
export type PublicationBlocked = { reason?: string; reason_code?: string; scientific_validation_artifact?: string };

export type StressRecord = {
  stress_periods?: number | null;
  shortfall_mwh?: number | null;
  shortfall_basis?: string | null;
  shortfall_upper_mwh?: number | null;
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

/** Spec 11.3 (R-D1): one raw-invariant check that failed, as the backend names it. */
export type RawInvariantFailure = {
  gate?: string;
  check?: string;
  name?: string;
  count?: number | null;
  unit?: "rows" | "periods" | string | null;
  deviation_ids?: string[];
  deviations?: { id?: string; summary?: string | null }[];
};

/** The validation fields of a Run detail or listing row (both are optional: older backends send none). */
export type RunValidationFields = {
  raw_invariants?: { status?: string | null } | null;
  raw_invariant_failures?: RawInvariantFailure[] | null;
  methodology?: MethodologyRecord | null;
  energy_balance_status?: string | null;
  energy_balance?: EnergyBalanceRecord | null;
  stress?: StressRecord | null;
  advisories?: RunAdvisory[] | null;
  advisory_summary?: { count?: number; max_severity?: string | null; needs_review?: boolean } | null;
  /** R4 R-低2: true while the Run is unfinished; the list is re-evaluated on completion. */
  advisories_provisional?: boolean | null;
  result_publication?: ResultPublication | null;
  validation_gate?: ValidationGateRecord | null;
  publication_blocked?: PublicationBlocked | null;
  storage_invariant_status?: string | null;
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
      return { kind, profileId, tone: "info", text: CORRECTED_PROFILE_LABEL, title: tr("validation.profile.correctedTitle", { profile: profileId }) };
    case "doctoral":
      return {
        kind, profileId, tone: "caution", text: DOCTORAL_PROFILE_LABEL,
        title: tr("validation.profile.doctoralTitle"),
      };
    case "pre_profile":
      return { kind, tone: "muted", text: tr("validation.profile.preProfile"), title: tr("validation.profile.preProfileTitle") };
    case "unresolved":
      // Recorded after profiles existed, but the id is not in this catalogue: not a pre-fix Run.
      return { kind, tone: "muted", text: tr("validation.profile.notRecorded"), title: tr("validation.profile.unresolvedTitle") };
    case "other":
      return { kind, profileId, tone: "muted", text: text(methodology?.label) ?? tr("validation.profile.other", { profile: profileId }), title: tr("validation.profile.otherTitle", { profile: profileId }) };
    default:
      // Older backend: no methodology field at all. Degrade, do not guess (principle 3).
      return { kind, tone: "muted", text: tr("validation.profile.notRecorded"), title: tr("validation.profile.unreportedTitle") };
  }
}

export type CheckField = { tone: "ok" | "danger" | "caution" | "muted"; text: string; dot: boolean; title?: string };

/** F-P04-2 (designer ruling 2026-10-06); English text of "validation.conformantTitle". */
export const CONFORMANT_TITLE = en["validation.conformantTitle"];

/** Spec 2.3: the Energy balance status-bar field. */
export function energyBalanceField(status: unknown, enforcement?: unknown): CheckField {
  const reportOnly = typeof enforcement === "string" && enforcement.startsWith("report_only") ? tr("validation.reportOnlyTitle") : undefined;
  switch (status) {
    case "passed": return { tone: "ok", text: tr("validation.field.passed"), dot: true, title: reportOnly };
    case "failed": return { tone: "danger", text: tr("validation.field.failed"), dot: true, title: reportOnly };
    case "report_only": return { tone: "caution", text: tr("validation.field.reported"), dot: true, title: tr("validation.reportOnlyTitle") };
    case "reproduction_with_declared_deviations": return { tone: "caution", text: tr("validation.field.declaredDeviations"), dot: true, title: reportOnly };
    case "reproduction_conformant": return { tone: "ok", text: tr("validation.field.conformant"), dot: true, title: tr("validation.conformantTitle") };
    case "superseded_pre_fix": return { tone: "caution", text: tr("validation.field.superseded"), dot: true, title: tr("validation.field.supersededTitle") };
    case "not_evaluated": return { tone: "muted", text: tr("validation.field.notEvaluated"), dot: false, title: reportOnly };
    case undefined: case null: case "": return { tone: "muted", text: tr("validation.field.notRecorded"), dot: false };
    default: return { tone: "muted", text: String(status).replaceAll("_", " "), dot: false };
  }
}

/** The new validation vocabulary on the existing Contract check / Scientific validation fields; other values keep the plain label. */
export function legacyStatusField(status: string, recorded?: string | null): CheckField | null {
  if (status === "superseded_pre_fix") {
    const original = text(recorded);
    return {
      tone: "caution", text: tr("validation.field.superseded"), dot: true,
      title: original ? tr("validation.field.supersededRecorded", { status: original.replaceAll("_", " ") }) : tr("validation.field.supersededTitle"),
    };
  }
  if (status === "reproduction_with_declared_deviations") return { tone: "caution", text: tr("validation.field.declaredDeviations"), dot: true };
  if (status === "reproduction_conformant") return { tone: "ok", text: tr("validation.field.conformant"), dot: true, title: tr("validation.conformantTitle") };
  return null;
}

function periods(n: number): string {
  return tr("validation.periods", { count: n, n: formatNumber(n, 0) });
}

/** Spec 2.3: the Stress events status-bar field (A2). None is muted, never green. */
export function stressField(stress: StressRecord | null | undefined): CheckField {
  const stressPeriods = count(stress?.stress_periods);
  if (stressPeriods === undefined) return { tone: "muted", text: tr("validation.field.notRecorded"), dot: false };
  if (stressPeriods === 0) return { tone: "muted", text: tr("validation.field.none"), dot: false, title: tr("validation.stress.noneTitle") };
  const shortfall = shortfallDisplay(stress?.shortfall_mwh, stress?.shortfall_basis, stress?.shortfall_upper_mwh, formatEnergy);
  return {
    tone: "caution", dot: true,
    text: shortfall ? `${periods(stressPeriods)} · ${shortfall.text}` : periods(stressPeriods),
    title: shortfall ? shortfall.title ?? tr("validation.stress.recordedTitle") : tr("validation.stress.notRecordedTitle"),
  };
}

/**
 * F-P04-1 (designer ruling 2026-10-06): a shortfall of a Run that predates exact
 * stress accounting (shortfall_basis = lower_bound) is shown as "≥ x" with the
 * upper bound in the tooltip, on the status bar and on the window card alike.
 */
export function shortfallDisplay(
  mwh: unknown, basis: unknown, upperMwh: unknown,
  format: (value: number) => string | null = (value) => withUnit(formatNumber(value), "MWh"),
): { text: string; title?: string; lowerBound: boolean } | null {
  const value = finite(mwh);
  const text = value === undefined ? null : format(value);
  if (!text) return null;
  if (basis !== "lower_bound") return { text, lowerBound: false };
  const upper = finite(upperMwh);
  return {
    text: `≥ ${text}`, lowerBound: true,
    title: upper === undefined ? tr("validation.lowerBound") : tr("validation.lowerBoundUpper", { upper: withUnit(formatNumber(upper), "MWh") }),
  };
}

/** The failed raw invariants of a Run (spec 11.3); [] when none are recorded. */
export function rawInvariantFailures(run: RunValidationFields | null | undefined): RawInvariantFailure[] {
  return Array.isArray(run?.raw_invariant_failures) ? run.raw_invariant_failures.filter((row): row is RawInvariantFailure => Boolean(row && typeof row === "object")) : [];
}

/** R5 R-低2: a reproduction Run that is still running has not reached its raw-invariant check yet. */
export function publicationPending(publication: ResultPublication | null | undefined): boolean {
  return publication?.status === "withheld" && (publication.raw_invariants_status === "pending" || publication.reason_code === "GF_RESULTS_PENDING_RAW_INVARIANTS");
}

/** passed | failed | not_evaluated as recorded (detail, publication record or its reason code); undefined when absent. */
function rawInvariantStatus(run: RunValidationFields): string | undefined {
  const reason = text(run.result_publication?.reason_code);
  // R5 R-低2: an unfinished Run's check is pending, whatever partial record it has.
  if (publicationPending(run.result_publication)) return "pending";
  return text(run.raw_invariants?.status) ?? text(run.result_publication?.raw_invariants_status)
    ?? (reason === "GF_RESULTS_WITHHELD_RAW_INVARIANTS_FAILED" ? "failed" : reason === "GF_RESULTS_WITHHELD_RAW_INVARIANTS_NOT_EVALUATED" ? "not_evaluated" : undefined);
}

function failureName(failure: RawInvariantFailure): string {
  return text(failure.name) ?? text(failure.check) ?? tr("validation.raw.defaultName");
}

/** Spec 11.3: the doctoral-only "Raw invariants" status-bar field; null for every other profile. */
export function rawInvariantsField(run: RunValidationFields | null | undefined): CheckField | null {
  if (!run || profileKind(run.methodology) !== "doctoral") return null;
  const failures = rawInvariantFailures(run);
  const status = rawInvariantStatus(run);
  if (failures.length) {
    return { tone: "caution", dot: true, text: tr("validation.raw.failedCount", { count: failures.length }), title: failures.map(failureName).join("\n") };
  }
  switch (status) {
    case "passed": return { tone: "ok", dot: true, text: tr("validation.field.passed"), title: tr("validation.raw.passedTitle") };
    case "failed": return { tone: "caution", dot: true, text: tr("validation.field.failed"), title: tr("validation.raw.failedTitle") };
    case "not_evaluated": return { tone: "muted", dot: false, text: tr("validation.field.notEvaluated") };
    case "pending": return { tone: "muted", dot: false, text: tr("validation.field.pending"), title: tr("validation.raw.pendingTitle") };
    default: return { tone: "muted", dot: false, text: tr("validation.field.notRecorded") };
  }
}

function sizeText(failure: RawInvariantFailure): string {
  const n = count(failure.count);
  if (n === undefined) return "";
  return tr(failure.unit === "periods" ? "validation.size.periods" : "validation.size.rows", { count: n, n: formatNumber(n, 0) });
}

function stripStop(value: string): string {
  return value.replace(/[.\s]+$/, "");
}

/** Spec 11.3: the withheld notice names the raw invariant that failed and whether a declared deviation explains it. */
export function withheldBody(run: RunValidationFields): string {
  const failures = rawInvariantFailures(run);
  const sentences: string[] = [];
  failures.forEach((failure, index) => {
    sentences.push(tr(index === 0 ? "validation.withheld.first" : "validation.withheld.next", { name: failureName(failure), size: sizeText(failure) }));
    const deviations = (failure.deviations ?? []).filter((row) => text(row?.id));
    const ids = deviations.length ? deviations.map((row) => text(row.id)!) : (failure.deviation_ids ?? []).filter((id) => text(id));
    if (ids.length) {
      const summary = deviations.map((row) => text(row.summary ?? undefined)).find(Boolean);
      sentences.push(summary ? tr("validation.withheld.matchesSummary", { ids: ids.join(", "), summary: stripStop(summary) }) : tr("validation.withheld.matches", { ids: ids.join(", ") }));
    } else {
      sentences.push(tr("validation.withheld.noDeviation"));
    }
  });
  if (!failures.length) {
    const status = rawInvariantStatus(run);
    sentences.push(tr(status === "not_evaluated" || !status ? "validation.withheld.notEvaluated" : "validation.withheld.failed"));
  }
  sentences.push(tr("validation.withheld.ledger"));
  return sentences.join(" ");
}

export type NoticeId = "energy_balance_failed" | "validation_gate_failed" | "results_withheld" | "pre_fix" | "stress_events";
export type NoticeAction = "open_residuals" | "open_inspect" | "export_ledger" | "view_advisories" | "show_stress_events";
export type RunNotice = {
  id: NoticeId;
  tone: "danger" | "caution" | "info";
  title: string;
  body: string;
  actions: NoticeAction[];
  advisoryCount?: number;
  /** F-P04-3: the failed gates, listed one sentence each. */
  gates?: GateName[];
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
  return value ? value.replaceAll("_", " ") : tr("validation.originalNotRecorded");
}

function residualSentence(balance: EnergyBalanceRecord | null | undefined): string {
  // P0-4 S7: the gate is the A2 account (open periods, largest closing residual);
  // older reports carry the envelope counts instead.
  const account = balance?.balance_account;
  const lower = count(balance?.envelope_lower_violations);
  const upper = count(balance?.envelope_upper_violations);
  const accountOpen = count(account?.unexplained_open_periods) ?? count(account?.open_periods);
  const failing = accountOpen !== undefined && accountOpen > 0 ? accountOpen
    : lower === undefined && upper === undefined ? undefined : (lower ?? 0) + (upper ?? 0);
  const largest = formatEnergy(accountOpen ? finite(account?.max_abs_closing_residual_mwh) : finite(balance?.maximum_envelope_violation_mwh));
  const where = failing ? tr("validation.residual.where", { periods: periods(failing) }) : tr("validation.residual.wherePlain");
  const residual = failing && largest ? tr("validation.residual.largest", { largest }) : "";
  return tr("validation.residual.sentence", { where, largest: residual });
}

export type GateName = "run_invariants" | "energy_balance" | "storage_invariants";

/** F-P04-3: the name and one-sentence meaning of each validation gate. */
// P1 W5: dictionary messages (validation.gate.*) read in the interface language.
export const GATE_TEXT: Readonly<Record<GateName, { name: string; sentence: string }>> = Object.freeze(Object.defineProperties({} as Record<GateName, { name: string; sentence: string }>, Object.fromEntries((["run_invariants", "energy_balance", "storage_invariants"] as const).map((gate) => [gate, {
  enumerable: true,
  get: () => ({ name: tr(`validation.gate.${gate}`), sentence: tr(`validation.gate.${gate}.sentence`) }),
}]))));
const GATE_ORDER: readonly GateName[] = ["run_invariants", "energy_balance", "storage_invariants"];

/** The gates a Run failed (validation_gate.gates), in a fixed order; [] when the record is absent. */
export function failedGates(run: RunValidationFields | null | undefined): GateName[] {
  const gates = run?.validation_gate?.gates;
  if (!gates || typeof gates !== "object") return [];
  return GATE_ORDER.filter((gate) => gates[gate] === "failed");
}

/** F-P04-4: annual results blocked by a failed validation gate (production policy). */
export function gateBlockedPublication(run: RunValidationFields | null | undefined): boolean {
  return run?.publication_blocked?.reason_code === "GF_VALIDATION_GATE_FAILED";
}

/** F-P04-4: the sentence of the "Annual results not published" Callout. */
export function gateBlockedText(run: RunValidationFields | null | undefined): string {
  const gates = failedGates(run).map((gate) => GATE_TEXT[gate].name);
  const which = gates.length
    ? tr("validation.gateBlocked.some", { count: gates.length, gates: gates.join(", ") })
    : tr("validation.gateBlocked.one");
  return `${which} ${tr("validation.gateBlocked.tail")}`;
}

/** Spec 2.3: every notice that applies, most important first. The bar shows the first one. */
export function runNotices(run: RunValidationFields | null | undefined): RunNotice[] {
  if (!run) return [];
  const kind = profileKind(run.methodology);
  const notices: RunNotice[] = [];
  // 1. A failed validation gate (F-P04-3: any gate, storage limits included). Only the
  //    energy balance failed: the original wording. Without a gate record (older
  //    Runs) the energy-balance verdict alone decides; the doctoral profile's
  //    failure there is notice 2 (withheld), not a defect.
  const gates = failedGates(run);
  const energyBalanceNotice = (): RunNotice => ({ id: "energy_balance_failed", tone: "danger", title: tr("validation.notice.energyTitle"), body: residualSentence(run.energy_balance), actions: ["open_residuals"] });
  if (run.validation_gate?.status === "failed") {
    if (gates.length === 1 && gates[0] === "energy_balance") notices.push(energyBalanceNotice());
    else {
      notices.push({
        id: "validation_gate_failed", tone: "danger",
        title: gates.length ? tr("validation.notice.gateTitle", { gates: gates.map((gate) => GATE_TEXT[gate].name).join(", ") }) : tr("validation.notice.gateTitlePlain"),
        body: tr("validation.notice.unverified"), actions: ["open_residuals"], gates,
      });
    }
  } else if (!run.validation_gate && run.energy_balance_status === "failed" && kind !== "doctoral") {
    notices.push(energyBalanceNotice());
  }
  // 2. Q14: annual results of a reproduction Run that did not pass its raw invariants.
  if (publicationPending(run.result_publication)) {
    notices.push({
      id: "results_withheld", tone: "info", title: tr("validation.notice.pendingTitle"),
      body: tr("validation.notice.pendingBody"),
      actions: [],
    });
  } else if (run.result_publication?.status === "withheld") {
    notices.push({
      id: "results_withheld", tone: "caution", title: tr("validation.notice.withheldTitle"),
      // Spec 11.3 (R-D1): the raw invariant that actually failed, not a generic energy-balance claim.
      body: withheldBody(run),
      actions: ["open_inspect", "export_ledger"],
    });
  }
  // 3. A Run produced before the review fixes (no profile, or a superseded positive claim).
  if (kind === "pre_profile" || supersededFields(run)) {
    const advisoryCount = Array.isArray(run.advisories) ? run.advisories.length : count(run.advisory_summary?.count) ?? 0;
    notices.push({
      id: "pre_fix", tone: "caution", title: tr("validation.notice.preFixTitle"),
      body: tr("validation.notice.preFixBody", { status: originalValidationStatus(run) }),
      actions: ["view_advisories"], advisoryCount,
    });
  }
  // 4. A2 stress events: recorded, never blocking.
  const stressPeriods = count(run.stress?.stress_periods);
  if (stressPeriods !== undefined && stressPeriods > 0) {
    const shortfall = shortfallDisplay(run.stress?.shortfall_mwh, run.stress?.shortfall_basis, run.stress?.shortfall_upper_mwh, formatEnergy)?.text;
    notices.push({
      id: "stress_events", tone: "caution", title: tr("validation.notice.stressTitle", { periods: periods(stressPeriods) }),
      body: tr("validation.notice.stressBody", { shortfall: shortfall ? tr("validation.notice.stressShortfall", { shortfall }) : "" }),
      actions: ["show_stress_events"],
    });
  }
  return notices;
}

// R4 R-低4: "export_ledger" opens the ledger files in Inspect; it does not download.
// P1 W5: dictionary messages (validation.action.*) in the interface language.
export const NOTICE_ACTION_LABELS: Readonly<Record<NoticeAction, string>> = localizedTable<NoticeAction>({
  open_residuals: "validation.action.open_residuals",
  open_inspect: "validation.action.open_inspect",
  export_ledger: "validation.action.export_ledger",
  view_advisories: "validation.action.view_advisories",
  show_stress_events: "validation.action.show_stress_events",
});

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

/**
 * R-D11 (four-role report, round R1-5): the one-line summary of the advisories
 * that apply to a Run ("11 advisories apply to this Run · 7 high, 3 medium,
 * 1 info"); null when none apply. The list comes from the Run detail; the
 * listing row's advisory_summary gives the count while the detail loads.
 */
export function advisorySummaryText(run: RunValidationFields | null | undefined): string | null {
  const advisories = runAdvisories(run);
  const total = advisories.length || (count(run?.advisory_summary?.count) ?? 0);
  if (!total) return null;
  // R4 R-低2: an unfinished Run's list is re-evaluated against its frozen fleet and modules.
  const provisional = run?.advisories_provisional === true ? ` · ${tr("validation.advisoriesProvisional")}` : "";
  const bySeverity = new Map<string, number>();
  for (const advisory of advisories) {
    const severity = text(advisory.severity) ?? "unrated";
    bySeverity.set(severity, (bySeverity.get(severity) ?? 0) + 1);
  }
  const ordered = [...bySeverity.entries()].sort(([a], [b]) => (SEVERITY_ORDER.indexOf(a) + 1 || 99) - (SEVERITY_ORDER.indexOf(b) + 1 || 99));
  const breakdown = ordered.map(([severity, n]) => `${n} ${severity}`).join(", ");
  return `${tr("validation.advisories", { count: total })}${breakdown ? ` · ${breakdown}` : ""}${provisional}`;
}

/** English text of "validation.advisoriesProvisional". */
export const ADVISORIES_PROVISIONAL_NOTE = en["validation.advisoriesProvisional"];

/** The advisories of a Run detail; the listing row carries only the count. */
export function runAdvisories(run: RunValidationFields | null | undefined): RunAdvisory[] {
  return Array.isArray(run?.advisories) ? run.advisories.filter((item): item is RunAdvisory => Boolean(item && typeof item === "object" && text(item.id))) : [];
}

export type RawResidualRow = { boundary: string; rawStatus: string; maxResidual: string | null; periods: string | null };

/**
 * F-P04-5: the raw boundary verdict and residual of the energy-balance check,
 * shown only in Inspect's residual panel (never on the status bar). Null when
 * the Run recorded no energy-balance report.
 */
export function rawResidualRows(balance: EnergyBalanceRecord | null | undefined): RawResidualRow[] | null {
  if (!balance || typeof balance !== "object") return null;
  const residual = finite(balance.maximum_absolute_boundary_residual_mwh) ?? finite(balance.maximum_absolute_raw_residual_mwh);
  const periodCount = count(balance.periods);
  return [{
    boundary: text(balance.boundary_id) ?? text(balance.balance_account?.boundary_id) ?? tr("validation.residualRow.notRecorded"),
    rawStatus: (text(balance.raw_boundary_status) ?? tr("validation.residualRow.statusNotRecorded")).replaceAll("_", " "),
    maxResidual: residual === undefined ? null : withUnit(formatNumber(residual), "MWh"),
    periods: periodCount === undefined ? null : formatNumber(periodCount, 0),
  }];
}

/** R4 R-低10: Q14 withholds this Run's annual results (its annual resources answer 409). */
export function annualResultsWithheld(run: RunValidationFields | null | undefined): boolean {
  return run?.result_publication?.status === "withheld";
}

/** R5 R-低2: the VRE page of a reproduction Run that is still running. */
export const VRE_PENDING_TEXT = en["validation.vrePending"];
export const VRE_WITHHELD_TEXT = en["validation.vreWithheld"];
/** P1 W5: the two VRE notes in the interface language (the constants keep the English text). */
export function vrePendingText(): string { return tr("validation.vrePending"); }
export function vreWithheldText(): string { return tr("validation.vreWithheld"); }
