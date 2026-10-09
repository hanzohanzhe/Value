"use client";

import { Button, Callout } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
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

/** Spec 6: shown only when something is quarantined. P1 W4b: app/ui Callout
 * (attention = amber, an alert) and Buttons; wording from the dictionaries. */
export default function ModuleQuarantinePanel({ report, busy, onDisable, onRescan }: {
  report?: QuarantineReport | null;
  busy: string;
  onDisable: (row: QuarantineRow) => void;
  onRescan: () => void;
}) {
  const t = useT();
  const rows = quarantineRows(report) as QuarantineRow[];
  if (!rows.length && !report?.catalog_stale) return null;
  const rescan = <Button size="sm" variant={rows.length ? "ghost" : "primary"} disabled={Boolean(busy)} loading={busy === "rescan"} onClick={onRescan}>{busy === "rescan" ? t("modules.action.rescanning") : t("modules.action.rescan")}</Button>;
  return <Callout tone="attention" className="module-quarantine-panel" title={rows.length ? quarantineTitle(rows.length, rows, t) : t("modules.quarantine.staleTitle")}>
    <p>{rows.length ? quarantineIntro(rows.length, t) : t("modules.quarantine.staleBody")}</p>
    <ul className="quarantine-rows">{rows.map((row) => <li key={row.rowKey} className="value-new-control">
      <div className="quarantine-row-head"><b>{row.label}</b><span className="quarantine-error">{row.firstLine}</span><code>{row.errorCode}</code></div>
      {row.manifestFile && <p className="quarantine-manifest">{t("modules.quarantine.manifestFile")}: <code>{`modules/${row.manifestFile}`}</code>{row.sharedId && ` · ${t("modules.quarantine.sharedId")}`}</p>}
      {row.details && <details><summary>{t("modules.quarantine.fullError")}</summary><pre>{row.details}</pre></details>}
      {!row.canDisable && row.correctiveAction && <p className="quarantine-help">{row.correctiveAction}</p>}
      <div className="quarantine-actions">
        {row.canDisable && <Button size="sm" variant="primary" disabled={Boolean(busy)} loading={busy === row.key} onClick={() => { if (window.confirm(disableConfirmation(row.id ?? row.label, row.kind, t))) onDisable(row); }}>{busy === row.key ? t("modules.action.disabling") : t("modules.action.disable")}</Button>}
        {rescan}
      </div>
    </li>)}</ul>
    {!rows.length && <div className="quarantine-actions">{rescan}</div>}
    <p className="quarantine-help">{t("modules.quarantine.offlineRecovery")}</p>
  </Callout>;
}
