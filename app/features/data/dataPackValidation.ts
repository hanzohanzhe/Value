// Data-pack validation panel (spec 11.2, S-D2). Pure logic over the backend's
// three-layer report (GET /api/data-packs/<id>/validation) or, until it has
// loaded, the cached layer summary of the pack listing (plausibility_status).
// The backend decides every finding and every profile's eligibility; this
// module only turns them into pills, a worst status and a details list.
import type { PillTone } from "../shared/Callout.tsx";

export type LayerFinding = { code?: string; layer?: string; role?: string | null; message?: string };
export type ProfileEligibility = { eligible?: boolean; pack_class?: string; blocking_codes?: string[]; warning_codes?: string[] };
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

const LAYER_LABELS: Record<LayerKey, string> = { structural: "Structural", chronology: "Chronology", plausibility: "Plausibility" };
const NOT_EVALUATED: Pill = { tone: "muted", text: "Not evaluated" };
const OBJECT_PREFIX = /^([A-Za-z0-9_.\-/]+):\s+([\s\S]+)$/;

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

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

export function profileLabel(profileId: string): string {
  if (profileId === "doctoral-lineage-0.6.0a2") return "Doctoral reproduction";
  if (profileId === "value-corrected" || profileId.startsWith("value-corrected-")) return "Corrected";
  return profileId;
}

/** Which profiles each code blocks (profile_eligibility[*].blocking_codes). */
function blockingProfiles(eligibility: Record<string, ProfileEligibility> | null | undefined): Map<string, string[]> {
  const result = new Map<string, string[]>();
  for (const [profile, row] of Object.entries(eligibility ?? {})) {
    for (const code of list(row?.blocking_codes)) result.set(code, [...(result.get(code) ?? []), profileLabel(profile)]);
  }
  return result;
}

function findingLayer(key: "chronology" | "plausibility", rows: LayerFinding[], blocking: Map<string, string[]>): LayerView {
  const details: DetailRow[] = rows.map((row) => ({
    code: String(row.code ?? "GF_DATA_FINDING"), object: row.role ? String(row.role) : null,
    message: String(row.message ?? ""), severity: blocking.has(String(row.code)) ? "error" : "warning",
  }));
  if (!details.length) return { key, label: LAYER_LABELS[key], pill: { tone: "ok", text: "Passed" }, rows: [] };
  const blocked = [...new Set(details.flatMap((row) => blocking.get(row.code) ?? []))];
  const pill: Pill = blocked.length
    ? { tone: "danger", text: "Failed", title: `${plural(details.length, "finding")}; blocks ${blocked.join(" and ")}` }
    : { tone: "caution", text: plural(details.length, "warning") };
  return { key, label: LAYER_LABELS[key], pill, rows: details };
}

/** Spec 11.2: Structural, Chronology and Plausibility of one pack, from the full report or the cached summary. */
export function validationLayers(report: DataPackValidationReport | null | undefined, cached?: CachedValidationStatus | null): LayerView[] {
  if (report && typeof report === "object" && typeof report.valid === "boolean") {
    const errors = list(report.errors).map((text) => ({ ...split(text), code: "GF_DATA_STRUCTURAL", severity: "error" as const }));
    const warnings = list(report.warnings).map((text) => ({ ...split(text), code: "GF_DATA_STRUCTURAL_WARNING", severity: "warning" as const }));
    const structuralPill: Pill = !report.valid
      ? { tone: "danger", text: "Failed", title: plural(errors.length, "error") }
      : warnings.length ? { tone: "caution", text: plural(warnings.length, "warning") } : { tone: "ok", text: "Passed" };
    const blocking = blockingProfiles(report.profile_eligibility);
    return [
      { key: "structural", label: LAYER_LABELS.structural, pill: structuralPill, rows: [...errors, ...warnings] },
      findingLayer("chronology", findings(report.layers?.chronology?.findings), blocking),
      findingLayer("plausibility", findings(report.layers?.plausibility?.findings), blocking),
    ];
  }
  if (cached && cached.status && cached.status !== "not_evaluated" && typeof cached.valid === "boolean") {
    const blocking = blockingProfiles(cached.profile_eligibility);
    const codeLayer = (key: "chronology" | "plausibility", codes: string[]) =>
      findingLayer(key, codes.map((code) => ({ code, message: "Recorded at the last validation; open the details after it reloads." })), blocking);
    return [
      { key: "structural", label: LAYER_LABELS.structural, pill: cached.valid ? { tone: "ok", text: "Passed" } : { tone: "danger", text: "Failed" }, rows: [] },
      codeLayer("chronology", list(cached.chronology_codes)),
      codeLayer("plausibility", list(cached.plausibility_codes)),
    ];
  }
  return (["structural", "chronology", "plausibility"] as const).map((key) => ({ key, label: LAYER_LABELS[key], pill: NOT_EVALUATED, rows: [] }));
}

/** The worst layer status, for "25/25 inputs present · validation {worst}". */
export function worstStatus(layers: readonly LayerView[]): WorstStatus {
  const tones = layers.map((layer) => layer.pill.tone);
  if (tones.includes("danger")) return "failed";
  if (tones.includes("caution")) return "warnings";
  if (tones.length && tones.every((tone) => tone === "ok")) return "passed";
  return "not_evaluated";
}

export const WORST_TEXT: Readonly<Record<WorstStatus, string>> = {
  failed: "failed", warnings: "passed with warnings", passed: "passed", not_evaluated: "not evaluated",
};

/** The text after the "25/25" count: "inputs present · validation {worst}". */
export function inputsPresentSuffix(worst: WorstStatus): string {
  return `inputs present · validation ${WORST_TEXT[worst]}`;
}

export type MethodologyUse = { profileId: string; label: string; pill: Pill };

/** Spec 11.2: whether each methodology profile may use this pack (profile_eligibility). */
export function methodologyUse(report: DataPackValidationReport | null | undefined, cached?: CachedValidationStatus | null): MethodologyUse[] {
  const source = report?.profile_eligibility ?? (cached?.status && cached.status !== "not_evaluated" ? cached.profile_eligibility : null);
  const structuralValid = typeof report?.valid === "boolean" ? report.valid : cached?.valid;
  const rows = Object.entries(source ?? {});
  const known = rows.length ? rows : [["value-corrected", null], ["doctoral-lineage-0.6.0a2", null]] as [string, ProfileEligibility | null][];
  return known.map(([profileId, row]) => {
    if (!row) return { profileId, label: profileLabel(profileId), pill: NOT_EVALUATED };
    if (row.eligible) {
      const warnings = list(row.warning_codes);
      return { profileId, label: profileLabel(profileId), pill: { tone: "ok", text: "Eligible", title: warnings.length ? `With warnings: ${warnings.join(", ")}` : undefined } };
    }
    const blocking = list(row.blocking_codes);
    const reason = structuralValid === false ? "structural validation failed" : blocking.length ? `blocked by ${blocking.join(", ")}` : "not eligible under this profile's data method";
    return { profileId, label: profileLabel(profileId), pill: { tone: "caution", text: `Not eligible — ${reason}` } };
  });
}
