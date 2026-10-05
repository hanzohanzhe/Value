import type { ReactNode } from "react";
import { formatMoney as formatSharedMoney, formatNumber as formatSharedNumber } from "./format.ts";
import { VALUE_STATES } from "./valueStates.ts";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "blue" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function formatBytes(bytes?: number | null) {
  if (typeof bytes !== "number" || !Number.isFinite(bytes)) return VALUE_STATES.missing.text;
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}
/** Legacy signature kept for existing call sites; delegates to shared/format.ts.
 * A missing value renders the "—" state word, never 0 (P0-9 S1, F1-07). */
export function formatNumber(value?: number | null, digits = 2): string {
  return formatSharedNumber(value, digits) ?? VALUE_STATES.missing.text;
}
export function formatMoney(value?: number | null): string {
  return formatSharedMoney(value) ?? VALUE_STATES.missing.text;
}
export function labelFor(id: string) {
  const scientificLabels: Record<string, string> = {
    psm: "National ahead market / PSM",
    balancing: "Balancing / redispatch",
    weather_spatializer: "Weather spatialisation",
  };
  if (scientificLabels[id]) return scientificLabels[id];
  return id.split(".").at(-1)?.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase()) ?? id;
}
export function modelDisplayName(value?: string) {
  return value ?? "";
}
