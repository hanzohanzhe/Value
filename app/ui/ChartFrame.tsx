"use client";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { DataTable, type DataColumn } from "./DataTable.tsx";
import { chartHeightFor } from "./chartScale.ts";
import type { SeriesPattern } from "./chartPalette.ts";
import { useUiStrings } from "./useUiStrings.ts";
import "./ChartFrame.css";

export type LegendItem = { key: string; label: ReactNode; color: string; pattern?: SeriesPattern; line?: "solid" | "dashed" };

export type ChartTable<Row> = {
  caption: ReactNode;
  columns: readonly DataColumn<Row>[];
  rows: readonly Row[];
  rowKey: (row: Row) => string;
};

export type ChartSize = {
  width: number;
  height: number;
  /** SVG fill for a legend item: its colour, or the url() of its pattern. */
  fill: (key: string) => string;
};

const PATTERN_ID = (base: string, key: string) => `${base}-${key.replace(/[^a-zA-Z0-9_-]/g, "_")}`;

/** Spec 2.1: one frame for every chart.
 * - Measures its real width (ResizeObserver) and hands pixel sizes to the
 *   drawing, so 12 px axis text stays 12 px; no viewBox scaling.
 * - Height 220 px below 600 px wide, otherwise 300 px.
 * - HTML legend that wraps; patterns where colour alone is not enough.
 * - aria-label summary on the SVG and a "Show data table" toggle with the
 *   same data in a DataTable. */
export function ChartFrame<Row>({ title, summary, legend = [], table, children, width: fixedWidth, initialWidth = 640, className, actions }: {
  title: ReactNode;
  /** One or two sentences that say what the chart shows (screen readers). */
  summary: string;
  legend?: readonly LegendItem[];
  table?: ChartTable<Row>;
  children: (size: ChartSize) => ReactNode;
  /** Fixed width (tests, print); otherwise measured. */
  width?: number;
  /** Width assumed before the first measurement, for the reserved height. */
  initialWidth?: number;
  className?: string;
  actions?: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [measured, setMeasured] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const strings = useUiStrings();
  const id = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const base = `v-chart-${id}`;
  useEffect(() => {
    if (fixedWidth != null) return;
    const node = box.current;
    if (!node) return;
    const update = (value: number) => setMeasured(Math.max(0, Math.floor(value)));
    update(node.getBoundingClientRect().width);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => { for (const entry of entries) update(entry.contentRect.width); });
    observer.observe(node);
    return () => observer.disconnect();
  }, [fixedWidth]);
  const width = fixedWidth ?? measured;
  const height = chartHeightFor(width ?? initialWidth);
  const patterned = legend.filter((item) => item.pattern && item.pattern !== "solid");
  const fill = (key: string) => {
    const item = legend.find((entry) => entry.key === key);
    if (!item) return "currentColor";
    return item.pattern && item.pattern !== "solid" ? `url(#${PATTERN_ID(base, key)})` : item.color;
  };
  return <figure className={`v-chart${className ? ` ${className}` : ""}`}>
    <figcaption className="v-chart__head">
      <span className="v-chart__title">{title}</span>
      <span className="v-chart__actions">
        {actions}
        {table && <button type="button" className="v-chart__toggle" aria-expanded={showTable} aria-controls={`${base}-table`} onClick={() => setShowTable((open) => !open)}>
          {showTable ? strings.hideDataTable : strings.showDataTable}
        </button>}
      </span>
    </figcaption>
    {legend.length > 0 && <ul className="v-chart__legend">
      {legend.map((item) => <li key={item.key}>
        <span className={`v-swatch v-swatch--${item.pattern ?? "solid"}${item.line ? ` v-swatch--line v-swatch--${item.line}` : ""}`} style={{ ["--swatch" as string]: item.color }} aria-hidden="true" />
        <span>{item.label}</span>
      </li>)}
    </ul>}
    <div ref={box} className="v-chart__plot" style={{ minHeight: height }}>
      {width != null && width > 0 && <svg className="v-chart__svg" width={width} height={height} role="img" aria-label={summary}>
        {patterned.length > 0 && <defs>
          {patterned.map((item) => <pattern key={item.key} id={PATTERN_ID(base, item.key)} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform={item.pattern === "hatch" ? "rotate(45)" : undefined}>
            <rect width="6" height="6" style={{ fill: item.color, opacity: item.pattern === "dots" ? 0.35 : 0.55 }} />
            {item.pattern === "hatch"
              ? <line x1="0" y1="0" x2="0" y2="6" style={{ stroke: item.color, strokeWidth: 3 }} />
              : <circle cx="3" cy="3" r="1.5" style={{ fill: item.color }} />}
          </pattern>)}
        </defs>}
        {children({ width, height, fill })}
      </svg>}
    </div>
    {table && showTable && <div id={`${base}-table`} className="v-chart__table">
      <DataTable caption={table.caption} columns={table.columns} rows={table.rows} rowKey={table.rowKey} maxHeight="320px" />
    </div>}
  </figure>;
}
