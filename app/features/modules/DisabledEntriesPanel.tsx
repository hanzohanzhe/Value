"use client";

import { StatusPill } from "../shared/Callout";
import { Button } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import { enableFailureHint, removeConfirmation, type DisabledEntry } from "./disabledEntries.ts";
import "./module-quarantine.css";

export type EntryError = { code?: string; message: string };

/**
 * Spec 11.4 (M-D4, F-D3): every disabled or quarantined local module or
 * extension stays reachable on the Modules page, with Enable, Rescan and
 * Remove. An Enable failure shows the error of that attempt (a fresh scan)
 * with a Rescan button. P1 W4b: app/ui Buttons, wording from the dictionaries;
 * the R6 confirmations are unchanged in meaning.
 */
export default function DisabledEntriesPanel({ entries, busy, errors, onEnable, onRescan, onRemove, headingId = "disabled-entries-title" }: {
  entries: readonly DisabledEntry[];
  busy: string;
  errors: Readonly<Record<string, EntryError>>;
  onEnable: (entry: DisabledEntry) => void;
  onRescan: () => void;
  onRemove: (entry: DisabledEntry) => void;
  headingId?: string;
}) {
  const t = useT();
  if (!entries.length) return null;
  return <section className="panel disabled-entries value-new-control" aria-labelledby={headingId}>
    <header><div><span>{t("modules.disabled.eyebrow")}</span><h3 id={headingId}>{t("modules.disabled.title")}</h3></div><StatusPill tone="caution">{entries.length}</StatusPill></header>
    <ul className="quarantine-rows">{entries.map((entry) => {
      const error = errors[entry.key];
      return <li key={entry.key}>
        <div className="quarantine-row-head">
          <b>{entry.label}</b>
          <StatusPill tone={entry.state === "quarantined" ? "danger" : "muted"}>{t(entry.kind === "extension" ? "modules.kind.extension" : "modules.kind.module")} · {t(entry.state === "quarantined" ? "modules.state.quarantined" : "modules.state.disabled")}</StatusPill>
          {entry.errorCode && <code>{entry.errorCode}</code>}
        </div>
        {entry.message && <p className="quarantine-error">{entry.message}</p>}
        {entry.manifestFiles && entry.manifestFiles.length > 0 && <p className="quarantine-manifest">{t("modules.disabled.manifestFiles", { count: entry.manifestFiles.length })}: {entry.manifestFiles.map((file, index) => <span key={file}>{index > 0 && ", "}<code>{`modules/${file}`}</code></span>)}</p>}
        {entry.state === "quarantined" && !entry.canEnable && <p className="quarantine-help">{t("modules.disabled.fixThenRescan")}</p>}
        {error && <p className="disabled-entry-error" role="alert">{error.code && <code>{error.code}</code>} {error.message} <span>{enableFailureHint(entry, t)}</span></p>}
        <div className="quarantine-actions">
          <Button size="sm" variant="primary" disabled={Boolean(busy) || !entry.canEnable} disabledReason={entry.canEnable ? undefined : t("modules.disabled.enableUnavailable")} loading={busy === `enable:${entry.key}`} onClick={() => onEnable(entry)}>{busy === `enable:${entry.key}` ? t("modules.action.enabling") : t("modules.action.enable")}</Button>
          <Button size="sm" variant="ghost" disabled={Boolean(busy)} loading={busy === "rescan"} onClick={onRescan}>{busy === "rescan" ? t("modules.action.rescanning") : t("modules.action.rescan")}</Button>
          <Button size="sm" variant="danger" disabled={Boolean(busy) || !entry.canRemove} loading={busy === `remove:${entry.key}`} onClick={() => { if (window.confirm(removeConfirmation(entry, t))) onRemove(entry); }}>{busy === `remove:${entry.key}` ? t("modules.action.removing") : t("modules.action.remove")}</Button>
        </div>
      </li>;
    })}</ul>
  </section>;
}
