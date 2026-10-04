import type { ReactNode } from "react";

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "good" | "warn" | "blue" }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function formatBytes(bytes = 0) {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}
export function formatNumber(value?: number, digits = 2) {
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: digits }).format(value ?? 0);
}
export function formatMoney(value = 0) {
  const absolute = Math.abs(value);
  if (absolute >= 1e9) return `£${formatNumber(value / 1e9, 3)}bn`;
  if (absolute >= 1e6) return `£${formatNumber(value / 1e6, 3)}m`;
  if (absolute >= 1e3) return `£${formatNumber(value / 1e3, 3)}k`;
  return `£${formatNumber(value, 2)}`;
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
