// Data page (P1 W4b, spec 6.3): the order of its sections. The inputs of the
// selected context come first; installers, the expert Data Workbench and the
// adapter guide (moved here from /extensions, D-W3-5) follow.
import type { MessageKey } from "../../i18n/index.ts";

export const DATA_PAGE_SECTIONS = [
  { id: "data-inputs", label: "data.nav.inputs" },
  { id: "data-install", label: "data.nav.install" },
  { id: "data-workbench-section", label: "data.nav.workbench" },
  { id: "data-adapters", label: "data.nav.adapters" },
] as const satisfies readonly { id: string; label: MessageKey }[];

/** One preview cell: missing stays a dash, objects are shown as compact JSON. */
export function previewCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

/** The bounded preview's sample as rows of cells under the union of their keys (first-seen order). */
export function previewSampleTable(sample: unknown): { columns: string[]; rows: { id: string; cells: Record<string, string> }[] } | null {
  if (!Array.isArray(sample) || !sample.length || !sample.every((row) => row && typeof row === "object" && !Array.isArray(row))) return null;
  const columns: string[] = [];
  for (const row of sample as Record<string, unknown>[]) for (const key of Object.keys(row)) if (!columns.includes(key)) columns.push(key);
  return {
    columns,
    rows: (sample as Record<string, unknown>[]).map((row, index) => ({ id: String(index + 1), cells: Object.fromEntries(columns.map((column) => [column, previewCell(row[column])])) })),
  };
}
