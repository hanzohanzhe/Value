"use client";

import { StatusPill } from "../shared/Callout";
import { removeConfirmation, type DisabledEntry } from "./disabledEntries.ts";
import "./module-quarantine.css";

export type EntryError = { code?: string; message: string };

/**
 * Spec 11.4 (M-D4, F-D3): every disabled or quarantined local module or
 * extension stays reachable below the module list, with Enable, Rescan and
 * Remove. An Enable failure shows the error of that attempt (a fresh scan)
 * with a Rescan button.
 */
export default function DisabledEntriesPanel({ entries, busy, errors, onEnable, onRescan, onRemove }: {
  entries: readonly DisabledEntry[];
  busy: string;
  errors: Readonly<Record<string, EntryError>>;
  onEnable: (entry: DisabledEntry) => void;
  onRescan: () => void;
  onRemove: (entry: DisabledEntry) => void;
}) {
  if (!entries.length) return null;
  return <section className="panel disabled-entries value-new-control" aria-labelledby="disabled-entries-title">
    <header><div><span>Local code that is not running</span><h3 id="disabled-entries-title">Disabled and quarantined</h3></div><StatusPill tone="caution">{entries.length}</StatusPill></header>
    <ul className="quarantine-rows">{entries.map((entry) => {
      const error = errors[entry.key];
      return <li key={entry.key}>
        <div className="quarantine-row-head">
          <b>{entry.label}</b>
          <StatusPill tone={entry.state === "quarantined" ? "danger" : "muted"}>{entry.kind === "extension" ? "Extension" : "Module"} · {entry.state === "quarantined" ? "Quarantined" : "Disabled"}</StatusPill>
          {entry.errorCode && <code>{entry.errorCode}</code>}
        </div>
        {entry.message && <p className="quarantine-error">{entry.message}</p>}
        {entry.state === "quarantined" && !entry.canEnable && <p className="quarantine-help">Fix the source, then Rescan. Remove takes it out of the scanned folders.</p>}
        {error && <p className="disabled-entry-error" role="alert">{error.code && <code>{error.code}</code>} {error.message} <span>This is the result of the Enable attempt just made. Fix the cause, then Rescan.</span></p>}
        <div className="quarantine-actions">
          <button type="button" className="value-action-primary" disabled={Boolean(busy) || !entry.canEnable} title={entry.canEnable ? undefined : "Quarantined entries are already enabled: fix the source, then Rescan."} onClick={() => onEnable(entry)}>{busy === `enable:${entry.key}` ? "Enabling…" : "Enable"}</button>
          <button type="button" className="value-action-link" disabled={Boolean(busy)} onClick={onRescan}>{busy === "rescan" ? "Rescanning…" : "Rescan"}</button>
          <button type="button" className="value-action-link danger" disabled={Boolean(busy) || !entry.canRemove} onClick={() => { if (window.confirm(removeConfirmation(entry))) onRemove(entry); }}>{busy === `remove:${entry.key}` ? "Removing…" : "Remove"}</button>
        </div>
      </li>;
    })}</ul>
  </section>;
}
