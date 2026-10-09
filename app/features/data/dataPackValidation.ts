// Data-pack validation panel (spec 11.2, S-D2). Pure logic over the backend's
// three-layer report (GET /api/data-packs/<id>/validation) or, until it has
// loaded, the cached layer summary of the pack listing (plausibility_status).
// The backend decides every finding and every profile's eligibility; this
// module only turns them into pills, a worst status and a details list.
//
// P1 W4b (spec 3): the wording comes from the dictionaries (packValidation.*);
// every text function takes the page's translate function, English by default.
import type { PillTone } from "../shared/Callout.tsx";
import { translator, type MessageKey, type Translate } from "../../i18n/index.ts";

const ENGLISH = translator("en");

export type LayerFinding = { code?: string; layer?: string; role?: string | null; message?: string };
export type ProfileEligibility = {
  eligible?: boolean; pack_class?: string; blocking_codes?: string[]; warning_codes?: string[];
  /** N-1: the profile's data-pack whitelist (the same check as the Study editor); false = not admitted. */
  pack_supported?: boolean; pack_support_reason?: string | null;
};
export type DataPackValidationReport = {
  data_pack_id?: string;
  valid?: boolean;
  errors?: string[];
  warnings?: string[];
  layers?: { chronology?: { findings?: LayerFinding[] }; plausibility?: { findings?: LayerFinding[] } };
  profile_eligibility?: Record<string, ProfileEligibility> | null;
};
/** The listing's cached summary (backend/server.py cached_validation_status). */
export type CachedValidationStatus = {
  status?: "passed" | "findings" | "not_evaluated" | string;
  valid?: boolean;
  chronology_codes?: string[];
  plausibility_codes?: string[];
  profile_eligibility?: Record<string, ProfileEligibility> | null;
};

export type LayerKey = "structural" | "chronology" | "plausibility";
export type Pill = { tone: PillTone; text: string; title?: string };
export type LayerView = { key: LayerKey; label: string; pill: Pill; rows: DetailRow[] };
export type DetailRow = { code: string; object: string | null; message: string; severity: "error" | "warning" };
export type WorstStatus = "failed" | "warnings" | "passed" | "not_evaluated";

const LAYER_LABELS: Record<LayerKey, MessageKey> = { structural: "packValidation.structural", chronology: "packValidation.chronology", plausibility: "packValidation.plausibility" };
const notEvaluated = (t: Translate): Pill => ({ tone: "muted", text: t("packValidation.notEvaluated") });
const OBJECT_PREFIX = /^([A-Za-z0-9_.\-/]+):\s+([\s\S]+)$/;

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function findings(value: unknown): LayerFinding[] {
  return Array.isArray(value) ? value.filter((item): item is LayerFinding => Boolean(item && typeof item === "object")) : [];
}

function split(message: string): { object: string | null; message: string } {
  const match = OBJECT_PREFIX.exec(message.trim());
  return match ? { object: match[1], message: match[2] } : { object: null, message: message.trim() };
}

export function profileLabel(profileId: string, t: Translate = ENGLISH): string {
  if (profileId === "doctoral-lineage-0.6.0a2") return t("packValidation.profile.doctoral");
  if (profileId === "value-corrected" || profileId.startsWith("value-corrected-")) return t("packValidation.profile.corrected");
  return profileId;
}

/** Which profiles each code blocks (profile_eligibility[*].blocking_codes). */
function blockingProfiles(eligibility: Record<string, ProfileEligibility> | null | undefined, t: Translate): Map<string, string[]> {
  const result = new Map<string, string[]>();
  for (const [profile, row] of Object.entries(eligibility ?? {})) {
    for (const code of list(row?.blocking_codes)) result.set(code, [...(result.get(code) ?? []), profileLabel(profile, t)]);
  }
  return result;
}

function findingLayer(key: "chronology" | "plausibility", rows: LayerFinding[], blocking: Map<string, string[]>, t: Translate): LayerView {
  const details: DetailRow[] = rows.map((row) => ({
    code: String(row.code ?? "GF_DATA_FINDING"), object: row.role ? String(row.role) : null,
    message: String(row.message ?? ""), severity: blocking.has(String(row.code)) ? "error" : "warning",
  }));
  if (!details.length) return { key, label: t(LAYER_LABELS[key]), pill: { tone: "ok", text: t("packValidation.passed") }, rows: [] };
  const blocked = [...new Set(details.flatMap((row) => blocking.get(row.code) ?? []))];
  const pill: Pill = blocked.length
    ? { tone: "danger", text: t("packValidation.failed"), title: t("packValidation.findingsBlock", { count: details.length, profiles: blocked.join(t("packValidation.and")) }) }
    : { tone: "caution", text: t("packValidation.warnings", { count: details.length }) };
  return { key, label: t(LAYER_LABELS[key]), pill, rows: details };
}

/** Spec 11.2: Structural, Chronology and Plausibility of one pack, from the full report or the cached summary. */
export function validationLayers(report: DataPackValidationReport | null | undefined, cached?: CachedValidationStatus | null, t: Translate = ENGLISH): LayerView[] {
  if (report && typeof report === "object" && typeof report.valid === "boolean") {
    const errors = list(report.errors).map((text) => ({ ...split(text), code: "GF_DATA_STRUCTURAL", severity: "error" as const }));
    const warnings = list(report.warnings).map((text) => ({ ...split(text), code: "GF_DATA_STRUCTURAL_WARNING", severity: "warning" as const }));
    const structuralPill: Pill = !report.valid
      ? { tone: "danger", text: t("packValidation.failed"), title: t("packValidation.errors", { count: errors.length }) }
      : warnings.length ? { tone: "caution", text: t("packValidation.warnings", { count: warnings.length }) } : { tone: "ok", text: t("packValidation.passed") };
    const blocking = blockingProfiles(report.profile_eligibility, t);
    return [
      { key: "structural", label: t(LAYER_LABELS.structural), pill: structuralPill, rows: [...errors, ...warnings] },
      findingLayer("chronology", findings(report.layers?.chronology?.findings), blocking, t),
      findingLayer("plausibility", findings(report.layers?.plausibility?.findings), blocking, t),
    ];
  }
  if (cached && cached.status && cached.status !== "not_evaluated" && typeof cached.valid === "boolean") {
    const blocking = blockingProfiles(cached.profile_eligibility, t);
    const codeLayer = (key: "chronology" | "plausibility", codes: string[]) =>
      findingLayer(key, codes.map((code) => ({ code, message: t("packValidation.cached") })), blocking, t);
    return [
      { key: "structural", label: t(LAYER_LABELS.structural), pill: cached.valid ? { tone: "ok", text: t("packValidation.passed") } : { tone: "danger", text: t("packValidation.failed") }, rows: [] },
      codeLayer("chronology", list(cached.chronology_codes)),
      codeLayer("plausibility", list(cached.plausibility_codes)),
    ];
  }
  return (["structural", "chronology", "plausibility"] as const).map((key) => ({ key, label: t(LAYER_LABELS[key]), pill: notEvaluated(t), rows: [] }));
}

/** The worst layer status, for "25/25 inputs present · validation {worst}". */
export function worstStatus(layers: readonly LayerView[]): WorstStatus {
  const tones = layers.map((layer) => layer.pill.tone);
  if (tones.includes("danger")) return "failed";
  if (tones.includes("caution")) return "warnings";
  if (tones.length && tones.every((tone) => tone === "ok")) return "passed";
  return "not_evaluated";
}

const WORST_KEYS: Readonly<Record<WorstStatus, MessageKey>> = {
  failed: "packValidation.worst.failed", warnings: "packValidation.worst.warnings", passed: "packValidation.worst.passed", not_evaluated: "packValidation.worst.notEvaluated",
};
export const WORST_TEXT: Readonly<Record<WorstStatus, string>> = {
  failed: ENGLISH(WORST_KEYS.failed), warnings: ENGLISH(WORST_KEYS.warnings), passed: ENGLISH(WORST_KEYS.passed), not_evaluated: ENGLISH(WORST_KEYS.not_evaluated),
};

/** The text after the "25/25" count: "inputs present · validation {worst}". */
export function inputsPresentSuffix(worst: WorstStatus, t: Translate = ENGLISH): string {
  return t("packValidation.inputsPresent", { worst: t(WORST_KEYS[worst]) });
}

export type MethodologyUse = { profileId: string; label: string; pill: Pill };

/** Spec 11.2: whether each methodology profile may use this pack (profile_eligibility). */
export function methodologyUse(report: DataPackValidationReport | null | undefined, cached?: CachedValidationStatus | null, t: Translate = ENGLISH): MethodologyUse[] {
  const source = report?.profile_eligibility ?? (cached?.status && cached.status !== "not_evaluated" ? cached.profile_eligibility : null);
  const structuralValid = typeof report?.valid === "boolean" ? report.valid : cached?.valid;
  const rows = Object.entries(source ?? {});
  const known = rows.length ? rows : [["value-corrected", null], ["doctoral-lineage-0.6.0a2", null]] as [string, ProfileEligibility | null][];
  return known.map(([profileId, row]) => {
    if (!row) return { profileId, label: profileLabel(profileId, t), pill: notEvaluated(t) };
    if (row.eligible) {
      const warnings = list(row.warning_codes);
      return { profileId, label: profileLabel(profileId, t), pill: { tone: "ok", text: t("packValidation.eligible"), title: warnings.length ? t("packValidation.eligibleWithWarnings", { codes: warnings.join(", ") }) : undefined } };
    }
    // N-1: a pack outside the profile's whitelist is refused by the Study editor whatever its layers say.
    const unsupported = row.pack_supported === false ? (row.pack_support_reason || t("packValidation.notThesisPack")) : null;
    const blocking = list(row.blocking_codes).filter((code) => !unsupported || code !== "VALUE_PROFILE_COMBINATION_UNSUPPORTED");
    const reason = unsupported ?? (structuralValid === false ? t("packValidation.structuralFailed") : blocking.length ? t("packValidation.blockedBy", { codes: blocking.join(", ") }) : t("packValidation.notEligibleMethod"));
    return { profileId, label: profileLabel(profileId, t), pill: { tone: "caution", text: t("packValidation.notEligible", { reason }) } };
  });
}
