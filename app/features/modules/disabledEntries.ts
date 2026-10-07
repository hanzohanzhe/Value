// "Disabled and quarantined" area of the Modules page (spec 11.4, M-D4, F-D3).
// Pure logic: every disabled or quarantined local module or extension becomes
// one row with its way back (Enable, Rescan, Remove). The backend decides the
// state; this module only lists it.
import { quarantineRows, sanitizeMessage } from "./module-quarantine.mjs";
import type { QuarantineReport, QuarantineRow } from "./ModuleQuarantinePanel";

type ModuleRecord = { module_id: string; name?: string; module_version: string; enabled: boolean; slot?: string };
type ExtensionRecord = { extension_id: string; name?: string; version: string; enabled: boolean; installed_at?: string };

export type EntryKind = "module" | "extension";
export type DisabledEntry = {
  key: string;
  kind: EntryKind;
  id: string;
  label: string;
  state: "disabled" | "quarantined";
  /** The latest scan's quarantine reason (never a cached Enable error). */
  errorCode?: string;
  message?: string;
  /** Enable is offered only for a disabled entry; a quarantined one needs a fix and Rescan. */
  canEnable: boolean;
  canRemove: boolean;
  /** R4 M-低4: the manifest files behind a quarantined entry (relative to modules/). */
  manifestFiles?: string[];
};

/** R4 F-低2: an entry names its ID, since two installed entries may share a display name. */
export function entryLabel(name: string | undefined, id: string, version: string): string {
  const shown = name && name !== id ? `${name} · ${id}` : id;
  return `${shown} ${version}`.trim();
}

const VERSION = /^(\d+)\.(\d+)\.(\d+)/;
function versionKey(value: string): number[] {
  const match = VERSION.exec(String(value));
  return match ? match.slice(1).map(Number) : [-1, -1, -1];
}
function newer(a: string, b: string): boolean {
  const [x, y] = [versionKey(a), versionKey(b)];
  for (let index = 0; index < 3; index += 1) if (x[index] !== y[index]) return x[index] > y[index];
  return false;
}

/** The current (highest-version) record of each installed extension, as the backend's lifecycle uses. */
export function currentExtensionRecords(records: readonly ExtensionRecord[] | null | undefined): ExtensionRecord[] {
  const byId = new Map<string, ExtensionRecord>();
  for (const record of records ?? []) {
    if (!record?.extension_id) continue;
    const current = byId.get(record.extension_id);
    if (!current || newer(record.version, current.version)) byId.set(record.extension_id, record);
  }
  return [...byId.values()];
}

export function disabledEntries({ modules, extensions, quarantine }: {
  modules?: readonly ModuleRecord[] | null;
  extensions?: readonly ExtensionRecord[] | null;
  quarantine?: QuarantineReport | null;
}): DisabledEntry[] {
  const rows = new Map<string, DisabledEntry>();
  for (const record of modules ?? []) {
    if (!record?.module_id || record.enabled) continue;
    const key = `module:${record.module_id}`;
    rows.set(key, { key, kind: "module", id: record.module_id, label: entryLabel(record.name, record.module_id, record.module_version), state: "disabled", canEnable: true, canRemove: true });
  }
  for (const record of currentExtensionRecords(extensions)) {
    if (record.enabled) continue;
    const key = `extension:${record.extension_id}`;
    rows.set(key, { key, kind: "extension", id: record.extension_id, label: entryLabel(record.name, record.extension_id, record.version), state: "disabled", canEnable: true, canRemove: true });
  }
  for (const row of quarantineRows(quarantine) as QuarantineRow[]) {
    if (!row.id) continue;
    const key = `${row.kind}:${row.id}`;
    const existing = rows.get(key);
    const manifestFiles = [...(existing?.manifestFiles ?? []), ...(row.manifestFile ? [row.manifestFile] : [])];
    rows.set(key, {
      key, kind: row.kind, id: row.id, label: existing?.label ?? row.label, state: "quarantined",
      errorCode: row.errorCode, message: sanitizeMessage(row.firstLine),
      canEnable: Boolean(existing?.canEnable), canRemove: true,
      ...(manifestFiles.length ? { manifestFiles } : {}),
    });
  }
  return [...rows.values()].sort((a, b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id));
}

export function removeConfirmation(entry: Pick<DisabledEntry, "kind" | "id">): string {
  return `Remove ${entry.kind} ${entry.id}? VALUE moves its installed files out of the scanned folders (to modules/disabled-manifests/removed/); they are not deleted. Install it again to use it.`;
}

export function lifecyclePath(entry: Pick<DisabledEntry, "kind" | "id">, action: "enable" | "remove"): string {
  return `/${entry.kind === "extension" ? "extensions" : "modules"}/${encodeURIComponent(entry.id)}/${action}`;
}

export type ModuleSourceChange = { module_id: string; installed_sha256: string; current_sha256: string };
export type InstalledModuleCard = {
  state: "enabled" | "disabled" | "quarantined";
  stateText: string;
  /** M2-N4: the card's own Enable/Disable toggle only for a healthy enabled module; the area below handles the rest. */
  offerToggle: boolean;
  /** M-D2: the in-place source edit, if any (spec 11.7 wording). */
  sourceChange: string | null;
};

/**
 * M2-N4 / M-D2 (four-role report, round R1-5): what one installed module's card
 * says. A quarantined or disabled module does not read "Conformance passed" with
 * an unrelated toggle; it names its state and points to the Disabled and
 * quarantined area, which owns Enable, Rescan and Remove.
 */
export function installedModuleCard(installation: Pick<ModuleRecord, "module_id" | "enabled">, quarantine: QuarantineReport | null | undefined, sourceChanges: readonly ModuleSourceChange[] | null | undefined): InstalledModuleCard {
  const quarantined = (quarantineRows(quarantine) as QuarantineRow[]).some((row) => row.kind === "module" && row.id === installation.module_id);
  const change = (sourceChanges ?? []).find((row) => row.module_id === installation.module_id);
  // R3M-5 (round R2): a quarantined module cannot run, so it does not promise a recorded hash yet.
  const changed = change ? `Source changed since install (${change.installed_sha256.slice(0, 8)}… → ${change.current_sha256.slice(0, 8)}…).` : null;
  const sourceChange = changed && (quarantined ? `${changed} It is quarantined, so no Run can start; once it is repaired, Runs record the new source hash.` : `${changed} Runs record the new source hash.`);
  if (quarantined) return { state: "quarantined", stateText: "Quarantined — see Disabled and quarantined below", offerToggle: false, sourceChange };
  if (!installation.enabled) return { state: "disabled", stateText: "Disabled — enable it in Disabled and quarantined below", offerToggle: false, sourceChange };
  return { state: "enabled", stateText: "Enabled", offerToggle: true, sourceChange };
}

export type ExtensionSourceChange = { extension_id: string; implementation: string; installed_sha256: string; current_sha256: string };

/**
 * R4 F-中2: an installed extension edited in place says so on its card, as a
 * module does (A16-4: accepted and recorded). Null when its source is unchanged.
 */
export function extensionSourceChangeNote(extensionId: string, changes: readonly ExtensionSourceChange[] | null | undefined): string | null {
  const rows = (changes ?? []).filter((row) => row.extension_id === extensionId);
  if (!rows.length) return null;
  const files = rows.map((row) => `${row.implementation} ${row.installed_sha256.slice(0, 8)}… → ${row.current_sha256.slice(0, 8)}…`).join("; ");
  return `Source changed since install (${files}). Results may change; Runs record the new source hash.`;
}

/**
 * R3M-4 (round R2): the card's note about saved Studies that select the module.
 * Only an enabled module's Disable is blocked by them; a disabled or
 * quarantined one (the quarantine area may disable it while Studies use it)
 * instead stops those Studies from running until it is enabled again.
 */
export function moduleUsageNote(state: InstalledModuleCard["state"], studyCount: number): string | null {
  if (studyCount <= 0) return null;
  const used = `Used by ${studyCount} saved ${studyCount === 1 ? "Study" : "Studies"}`;
  if (state === "enabled") return `${used}; disable is blocked until those configurations are migrated.`;
  const they = studyCount === 1 ? "it cannot" : "they cannot";
  return `${used}; ${they} run until this module is ${state === "quarantined" ? "repaired" : "enabled again"}, or ${studyCount === 1 ? "it selects" : "they select"} another module.`;
}

/**
 * R3M-3 (round R2): what to do after a failed Enable. Rescan alone does not
 * enable a disabled entry; Enable scans afresh, so it is the step to repeat
 * whenever the entry offers Enable.
 */
export function enableFailureHint(entry: Pick<DisabledEntry, "canEnable">): string {
  return entry.canEnable
    ? "This is the result of the Enable attempt just made. Fix the cause, then press Enable again (Enable scans afresh; Rescan alone leaves a disabled entry disabled)."
    : "This is the result of the Enable attempt just made. Fix the cause, then Rescan.";
}
