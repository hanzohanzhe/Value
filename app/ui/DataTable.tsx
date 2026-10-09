import type { ReactNode } from "react";
import { UI_STRINGS } from "./strings.ts";
import { stableRowKeys } from "./rowKeys.ts";
export { stableRowKeys } from "./rowKeys.ts";
import "./DataTable.css";

export type DataColumn<Row> = {
  key: string;
  header: ReactNode;
  /** Numeric columns are right-aligned with tabular figures (spec 2). */
  numeric?: boolean;
  /** The first column may name the row (`th scope="row"`). */
  rowHeader?: boolean;
  render: (row: Row) => ReactNode;
  className?: string;
};

/** Spec 2: caption, scoped headers, sticky header, numeric columns aligned,
 * a focusable labelled scroll container instead of a page-wide min-width, and
 * row keys from a stable ID only. */
export function DataTable<Row>({ caption, columns, rows, rowKey, scrollLabel, empty, captionHidden = false, className, maxHeight }: {
  caption: ReactNode;
  columns: readonly DataColumn<Row>[];
  rows: readonly Row[];
  /** Stable ID of a row; never a business field that may repeat. */
  rowKey: (row: Row) => string;
  /** Accessible name of the scroll region; defaults to the caption text. */
  scrollLabel?: string;
  /** Shown instead of the table when there are no rows (an EmptyState). */
  empty?: ReactNode;
  captionHidden?: boolean;
  className?: string;
  /** Scroll vertically inside the container beyond this height (CSS length). */
  maxHeight?: string;
}) {
  if (!rows.length && empty != null) return <>{empty}</>;
  const label = scrollLabel ?? (typeof caption === "string" ? caption : UI_STRINGS.scrollTable);
  const { keys, duplicates } = stableRowKeys(rows, rowKey);
  if (duplicates.length && process.env.NODE_ENV !== "production") console.error(`DataTable: duplicate row keys ${duplicates.join(", ")}; rowKey must return a stable unique ID`);
  return <div className={`v-table-scroll${className ? ` ${className}` : ""}`} tabIndex={0} role="region" aria-label={label} style={maxHeight ? { maxHeight } : undefined}>
    <table className="v-table">
      <caption className={captionHidden ? "v-visually-hidden" : undefined}>{caption}</caption>
      <thead>
        <tr>{columns.map((column) => <th key={column.key} scope="col" className={column.numeric ? "v-num" : undefined}>{column.header}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, index) => <tr key={keys[index]}>
          {columns.map((column) => {
            const cellClass = [column.numeric ? "v-num" : "", column.className ?? ""].filter(Boolean).join(" ") || undefined;
            return column.rowHeader
              ? <th key={column.key} scope="row" className={cellClass}>{column.render(row)}</th>
              : <td key={column.key} className={cellClass}>{column.render(row)}</td>;
          })}
        </tr>)}
      </tbody>
    </table>
  </div>;
}
