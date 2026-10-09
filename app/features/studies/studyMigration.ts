import { apiFetch } from "../../lib/api.ts";
import { localizedTable, tr, type MessageKey } from "../../i18n/index.ts";

// Saved-Study migration after a code or method change (spec 7; plan X0 S11/S12;
// DECISIONS Q13). gridform_core/revision_migration classifies the change; the
// browser only shows it: code-only changes were appended by the server and get
// one info line, method/data changes need the user's explicit confirmation of
// the exact diff (diff_sha256) before any Run starts.

export type MigrationDifference = {
  dimension: string;
  key: string;
  old: unknown;
  new: unknown;
  classification: string;
  effect?: string;
  error_code?: string;
  hint?: string;
  matches_reference_preset?: string[];
};

export type MigrationProfileChoice = {
  profile_id: string;
  label: string;
  default: boolean;
  frozen: boolean;
  supported: boolean;
  unsupported_reasons: string[];
  matches_reference_preset: boolean;
};

export type RevisionMigration = {
  schema_version?: string;
  classification: string;
  declared_sha256?: string | null;
  calculated_sha256?: string | null;
  differences: MigrationDifference[];
  error_code?: string | null;
  automatic?: boolean;
  confirmable?: boolean;
  revision_reason?: string | null;
  diff_sha256: string;
  profile_choices?: MigrationProfileChoice[];
  selected_profile_id?: string;
};

export const CODE_ONLY_REASONS = new Set(["code-identity-upgrade", "environment-reidentify", "source-reidentify"]);

export function isRevisionMigration(value: unknown): value is RevisionMigration {
  if (!value || typeof value !== "object") return false;
  const record = value as RevisionMigration;
  return typeof record.classification === "string" && typeof record.diff_sha256 === "string" && Array.isArray(record.differences);
}

/** A classification the user must confirm (method, data or unverifiable); code-only and content changes are not. */
export function needsConfirmation(value: unknown): value is RevisionMigration {
  return isRevisionMigration(value) && value.confirmable === true && value.automatic !== true;
}

/** The classification carried by a refused Run start (409) or a preflight report. */
export function migrationFromResponse(payload: unknown): RevisionMigration | null {
  if (!payload || typeof payload !== "object") return null;
  const record = payload as { revision_migration?: unknown; checks?: { project_revision?: { classification?: unknown } } };
  const candidate = record.revision_migration ?? record.checks?.project_revision?.classification;
  return needsConfirmation(candidate) ? candidate : null;
}

/** Spec 7: the info line of a Study whose latest revision only re-identified the code. */
export function codeIdentityUpdate(project: { revision_reason?: string; revision_sha256?: string }): string | null {
  if (!project.revision_reason || !CODE_ONLY_REASONS.has(project.revision_reason) || !project.revision_sha256) return null;
  // R4 F-中2: installed local code edited in place is recorded, not "no change".
  if (project.revision_reason === "source-reidentify") return tr("studyMigration.codeEdited", { sha: project.revision_sha256.slice(0, 12) });
  return tr("studyMigration.codeOnly", { sha: project.revision_sha256.slice(0, 12) });
}

// P1 W5: dictionary messages (studyMigration.dim.*) in the interface language.
const DIMENSION_LABELS: Readonly<Record<string, string>> = localizedTable<string>({
  methodology: "studyMigration.dim.methodology",
  module: "studyMigration.dim.module",
  solver_contract: "studyMigration.dim.solver_contract",
  data: "studyMigration.dim.data",
  environment: "studyMigration.dim.environment",
  study: "studyMigration.dim.study",
  basis: "studyMigration.dim.basis",
  other: "studyMigration.dim.other",
} as Record<string, MessageKey>);

export function dimensionLabel(dimension: string): string {
  return DIMENSION_LABELS[dimension] ?? dimension.replaceAll("_", " ");
}

function profileLabel(id: string, choices: MigrationProfileChoice[] | undefined): string {
  return choices?.find((choice) => choice.profile_id === id)?.label ?? id;
}

/** A recorded value as short text; a missing value says so instead of showing nothing. */
export function migrationValueText(value: unknown, key = "", choices?: MigrationProfileChoice[]): string {
  if (value === null || value === undefined || value === "") return tr("studyMigration.notRecorded");
  if (typeof value === "string") return key === "profile_id" ? profileLabel(value, choices) : value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    if (!value.length) return tr("studyMigration.none");
    return value.length > 3 ? tr("studyMigration.items", { count: value.length }) : value.map((item) => migrationValueText(item)).join(", ");
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    if (typeof record.profile_id === "string") return profileLabel(record.profile_id, choices);
    if (typeof record.contract_version === "string") return record.contract_version;
    if (typeof record.version === "string") return record.version;
    return tr("studyMigration.object");
  }
  return String(value);
}

export type MigrationRow = { id: string; dimension: string; subject: string; before: string; after: string; effect: string };

export function migrationRows(migration: RevisionMigration): MigrationRow[] {
  return migration.differences.map((row, index) => ({
    id: `${row.dimension}:${row.key}:${index}`,
    dimension: dimensionLabel(row.dimension),
    subject: row.key.replaceAll("_", " "),
    before: migrationValueText(row.old, row.key, migration.profile_choices),
    after: migrationValueText(row.new, row.key, migration.profile_choices),
    effect: row.effect ?? "",
  }));
}

/** GET the read-only classification of a saved Study, optionally for a chosen methodology (nothing is written). */
export async function fetchRevisionMigration(apiBase: string, projectId: string, profileId?: string | null): Promise<RevisionMigration> {
  const query = profileId ? `?profile_id=${encodeURIComponent(profileId)}` : "";
  const response = await apiFetch(`${apiBase}/projects/${encodeURIComponent(projectId)}/revision-migration${query}`, { cache: "no-store" });
  const payload = await response.json() as { error?: string; revision_migration?: unknown };
  if (!response.ok || !isRevisionMigration(payload.revision_migration)) throw new Error(payload.error ?? tr("studyMigration.loadFailed"));
  return payload.revision_migration;
}

/**
 * The classification the confirmation dialog opens with (F-X0-2): when a
 * pre-profile Study matches a frozen profile's reference preset, the diff of
 * that profile is loaded first, so the preselected methodology and the
 * confirmed diff_sha256 agree. Any failure keeps the server's own selection.
 */
export async function openingMigration(apiBase: string, projectId: string, migration: RevisionMigration): Promise<RevisionMigration> {
  const preferred = preferredMigrationProfile(migration);
  if (!preferred || preferred === (migration.selected_profile_id ?? null)) return migration;
  try {
    return await fetchRevisionMigration(apiBase, projectId, preferred);
  } catch {
    return migration;
  }
}

/**
 * The methodology preselected when a pre-profile Study is migrated (F-X0-2):
 * the supported profile whose reference preset the Study matches, else the
 * server's selection (the default profile).
 */
export function preferredMigrationProfile(migration: RevisionMigration): string | null {
  const choices = migration.profile_choices ?? [];
  if (!choices.length) return null;
  const hinted = migration.differences.find((row) => row.hint === "matches_reference_preset")?.matches_reference_preset ?? [];
  const match = choices.find((choice) => choice.supported && (hinted.includes(choice.profile_id) || choice.matches_reference_preset));
  if (match) return match.profile_id;
  return migration.selected_profile_id ?? choices.find((choice) => choice.default)?.profile_id ?? null;
}
