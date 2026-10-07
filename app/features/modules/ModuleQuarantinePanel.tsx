"use client";

import { Callout } from "../shared/Callout";
import { disableConfirmation, quarantineIntro, quarantineRows, quarantineTitle } from "./module-quarantine.mjs";
import "./module-quarantine.css";

export type QuarantineEntry = {
  kind: string; id: string | null; manifest_file?: string; version?: string | null;
  error_code: string; error_type?: string; message?: string; corrective_action?: string;
};
export type QuarantineReport = { schema_version?: string; status: string; entries: QuarantineEntry[]; catalog_stale?: boolean };
/** One panel row as module-quarantine.mjs builds it. */
export type QuarantineRow = {
  key: string; rowKey: string; manifestFile: string | null; sharedId: boolean;
  kind: "module" | "extension"; id: string | null; label: string; errorCode: string;
  firstLine: string; details: string; canDisable: boolean; correctiveAction: string; disablePath: string | null;
};

/** Spec 6: shown only when something is quarantined. */
export default function ModuleQuarantinePanel({ report, busy, onDisable, onRescan }: {
  report?: QuarantineReport | null;
  busy: string;
  onDisable: (row: QuarantineRow) => void;
  onRescan: () => void;
}) {
  const rows = quarantineRows(report) as QuarantineRow[];
  if (!rows.length && !report?.catalog_stale) return null;
  return <Callout tone="caution" className="module-quarantine-panel" title={rows.length ? quarantineTitle(rows.length, rows) : "The module catalogue is out of date"}>
    <p>{rows.length ? quarantineIntro(rows.length) : "A module change could not be applied; new Runs are paused until a rescan succeeds."}</p>
    <ul className="quarantine-rows">{rows.map((row) => <li key={row.rowKey} className="value-new-control">
      <div className="quarantine-row-head"><b>{row.label}</b><span className="quarantine-error">{row.firstLine}</span><code>{row.errorCode}</code></div>
      {row.manifestFile && <p className="quarantine-manifest">Manifest file: <code>modules/{row.manifestFile}</code>{row.sharedId && " · another manifest uses the same ID; keep one and Rescan"}</p>}
      {row.details && <details><summary>Full error</summary><pre>{row.details}</pre></details>}
      {!row.canDisable && row.correctiveAction && <p className="quarantine-help">{row.correctiveAction}</p>}
      <div className="quarantine-actions">
        {row.canDisable && <button type="button" className="value-action-primary" disabled={Boolean(busy)} onClick={() => { if (window.confirm(disableConfirmation(row.id ?? row.label))) onDisable(row); }}>{busy === row.key ? "Disabling…" : "Disable"}</button>}
        <button type="button" className="value-action-link" disabled={Boolean(busy)} onClick={onRescan}>{busy === "rescan" ? "Rescanning…" : "Rescan"}</button>
      </div>
    </li>)}</ul>
    {!rows.length && <div className="quarantine-actions"><button type="button" className="value-action-primary" disabled={Boolean(busy)} onClick={onRescan}>{busy === "rescan" ? "Rescanning…" : "Rescan"}</button></div>}
    <p className="quarantine-help">If VALUE cannot start at all, the user guide section &quot;Offline module recovery&quot; gives the command that disables a module while VALUE is stopped.</p>
  </Callout>;
}
