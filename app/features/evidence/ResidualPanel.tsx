"use client";

// F-P04-5 (designer ruling 2026-10-06): the raw boundary residual of the
// energy-balance check, shown only here in Inspect. The status bar shows the
// A2 gate verdict; the raw verdict is evidence, not a second status.
import { rawResidualRows, type EnergyBalanceRecord } from "../workspace/runValidation.ts";
import { ValueState } from "../shared/Callout";
import { DataTable, type DataColumn } from "../../ui/DataTable.tsx";
import "./residual-panel.css";
import { useT } from "../../i18n/LocaleProvider";
import type { Translate } from "../../i18n/index.ts";

type ResidualRow = NonNullable<ReturnType<typeof rawResidualRows>>[number];
const columns = (t: Translate): DataColumn<ResidualRow>[] => [
  { key: "boundary", header: t("residual.col.boundary"), render: (row) => <code>{row.boundary}</code> },
  { key: "status", header: t("residual.col.status"), render: (row) => row.rawStatus },
  { key: "residual", header: t("residual.col.max"), numeric: true, render: (row) => row.maxResidual ?? <ValueState state="not_recorded" /> },
  { key: "periods", header: t("residual.col.periods"), numeric: true, render: (row) => row.periods ?? <ValueState state="not_recorded" /> },
];

export default function ResidualPanel({ balance }: { balance?: EnergyBalanceRecord | null }) {
  const t = useT();
  const rows = rawResidualRows(balance);
  return <section className="panel residual-panel value-new-control" aria-label={t("residual.label")}>
    <div className="panel-head"><div><span>{t("residual.kicker")}</span><h3>{t("residual.title")}</h3></div></div>
    {!rows ? <p className="residual-panel-note">{t("residual.none")}</p> : <>
      {/* W4c (spec 2): the shared DataTable - a focusable, labelled scroll region (axe: scrollable-region-focusable). */}
      <DataTable className="residual-table" caption={t("residual.caption")} captionHidden columns={columns(t)} rows={rows} rowKey={(row) => row.boundary} />
      <p className="residual-panel-note">{t("residual.note")}</p>
    </>}
  </section>;
}
