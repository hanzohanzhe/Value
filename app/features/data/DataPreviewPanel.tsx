"use client";

import { Button, DataTable, Disclosure } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import { previewCell, previewSampleTable } from "./dataPage.ts";
import type { DataPreview } from "./dataPageTypes";

/**
 * The bounded server preview of one bound role (P1 W4b, spec 6.3): facts,
 * columns and timestamps as text, numeric ranges, array counts and the sample
 * as tables; the raw preview only behind "Technical details" (no JSON on the
 * page itself, as for the mapping review, F4-13).
 */
export default function DataPreviewPanel({ preview, onClose }: { preview: DataPreview; onClose: () => void }) {
  const t = useT();
  const ranges = Object.entries(preview.numeric_ranges ?? {}).map(([column, range]) => ({ column, ...range }));
  const counts = Object.entries(preview.array_counts ?? {}).map(([key, value]) => ({ key, value }));
  const sample = previewSampleTable(preview.sample);
  return <section className="panel data-preview" aria-labelledby="data-preview-title">
    <div className="panel-head"><div><span>{t("data.preview.eyebrow")}</span><h3 id="data-preview-title">{preview.definition ?? preview.role}</h3></div><Button size="sm" variant="ghost" onClick={onClose}>{t("data.preview.close")}</Button></div>
    <div className="preview-facts">
      <span><small>{t("data.preview.status")}</small><b>{preview.status.replaceAll("_", " ")}</b></span>
      <span><small>{t("data.preview.format")}</small><b>{preview.format ?? t("data.preview.notBound")}</b></span>
      <span><small>{t("data.preview.sampledRows")}</small><b>{preview.sampled_rows ?? t("data.preview.metadataOnly")}</b></span>
      <span><small>{t("data.preview.duplicates")}</small><b>{preview.duplicate_sample_identities ?? t("data.preview.notEvaluated")}</b></span>
    </div>
    {preview.columns && <p><b>{t("data.preview.columns")}:</b> {preview.columns.join(", ")}</p>}
    {preview.timestamp_sample && <p><b>{t("data.preview.timestamps")}:</b> {preview.timestamp_sample.first ?? t("data.preview.none")} → {preview.timestamp_sample.last ?? t("data.preview.none")}</p>}
    {ranges.length > 0 && <DataTable caption={t("data.preview.ranges")} rows={ranges} rowKey={(row) => row.column} columns={[
      { key: "column", header: t("data.preview.rangeColumn"), rowHeader: true, render: (row) => row.column },
      { key: "minimum", header: t("data.preview.minimum"), numeric: true, render: (row) => previewCell(row.minimum) },
      { key: "maximum", header: t("data.preview.maximum"), numeric: true, render: (row) => previewCell(row.maximum) },
    ]} />}
    {counts.length > 0 && <DataTable caption={t("data.preview.counts")} rows={counts} rowKey={(row) => row.key} columns={[
      { key: "key", header: t("data.preview.countKey"), rowHeader: true, render: (row) => row.key },
      { key: "value", header: t("data.preview.countValue"), numeric: true, render: (row) => previewCell(row.value) },
    ]} />}
    {sample && <DataTable caption={t("data.preview.sample")} rows={sample.rows} rowKey={(row) => row.id} maxHeight="320px" columns={[
      { key: "#", header: t("data.preview.row"), numeric: true, render: (row) => row.id },
      ...sample.columns.map((column) => ({ key: `c:${column}`, header: column, render: (row: { cells: Record<string, string> }) => row.cells[column] })),
    ]} />}
    <Disclosure summary={t("data.preview.technical")}><pre>{JSON.stringify({ array_counts: preview.array_counts, numeric_ranges: preview.numeric_ranges, sample: preview.sample, source_sha256: preview.source_sha256 }, null, 2)}</pre></Disclosure>
    <small>{t("data.preview.note")}</small>
  </section>;
}
