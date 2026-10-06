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
};

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
    rows.set(key, { key, kind: "module", id: record.module_id, label: `${record.name ?? record.module_id} ${record.module_version}`.trim(), state: "disabled", canEnable: true, canRemove: true });
  }
  for (const record of currentExtensionRecords(extensions)) {
    if (record.enabled) continue;
    const key = `extension:${record.extension_id}`;
    rows.set(key, { key, kind: "extension", id: record.extension_id, label: `${record.name ?? record.extension_id} ${record.version}`.trim(), state: "disabled", canEnable: true, canRemove: true });
  }
  for (const row of quarantineRows(quarantine) as QuarantineRow[]) {
    if (!row.id) continue;
    const key = `${row.kind}:${row.id}`;
    const existing = rows.get(key);
    rows.set(key, {
      key, kind: row.kind, id: row.id, label: existing?.label ?? row.label, state: "quarantined",
      errorCode: row.errorCode, message: sanitizeMessage(row.firstLine),
      canEnable: Boolean(existing?.canEnable), canRemove: true,
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
