// F-P05A-1 (designer ruling 2026-10-06): the currency and EUR->GBP rate of a
// price-column mapping (P0-5a S10 backend: gridform_core/data_adapters.py,
// backend/data_mapping.py). Pure logic: the rate is declared by the user, never
// defaulted; the backend performs the conversion and reports both values.
// P1 W4b (spec 3): messages from the dictionaries (mapping.*), English by default.
import type { CsvMappingRole } from "./csvMappingTypes.ts";
import { translator, type MessageKey, type Translate } from "../../i18n/index.ts";

const ENGLISH = translator("en");

export type Currency = "GBP" | "EUR";
export const FX_BASES = ["annual average", "monthly average", "fixed rate"] as const;
export type FxDraft = { currency: Currency; eurPerGbp: string; fxBasis: string; priceYear: string };
export type FxRequest = { eur_per_gbp: number; fx_basis: string; price_year: number };
export type FxErrors = Partial<Record<"eurPerGbp" | "fxBasis" | "priceYear", string>>;

export const EMPTY_FX: FxDraft = { currency: "GBP", eurPerGbp: "", fxBasis: "", priceYear: "" };
export const PRICE_YEAR_RANGE = [1990, 2100] as const;

/** A price role declares the EUR source unit it accepts (catalog fx_required_for). */
export function acceptsEur(spec: Pick<CsvMappingRole, "fx_required_for"> | null | undefined): boolean {
  return Boolean(spec?.fx_required_for?.includes("EUR/MWh"));
}

/** Source units offered for one target unit and currency: GBP never offers a pair that needs a rate. */
export function sourceUnits(spec: Pick<CsvMappingRole, "conversion_pairs">, targetUnit: string, currency: Currency): string[] {
  const pairs = spec.conversion_pairs.filter((pair) => pair.target_unit === targetUnit && Boolean(pair.requires_fx) === (currency === "EUR"));
  return [...new Set(pairs.map((pair) => pair.source_unit))];
}

/** Field errors of an EUR mapping (GF_MAPPING_FX); none for GBP. */
export function fxErrors(draft: FxDraft, t: Translate = ENGLISH): FxErrors {
  if (draft.currency !== "EUR") return {};
  const errors: FxErrors = {};
  const rate = draft.eurPerGbp.trim();
  if (!/^\d+(\.\d{1,4})?$/.test(rate) || !(Number(rate) > 0)) errors.eurPerGbp = t("mapping.fxRate");
  if (!(FX_BASES as readonly string[]).includes(draft.fxBasis)) errors.fxBasis = t("mapping.fxBasisMissing");
  const year = draft.priceYear.trim();
  if (!/^\d{4}$/.test(year) || Number(year) < PRICE_YEAR_RANGE[0] || Number(year) > PRICE_YEAR_RANGE[1]) errors.priceYear = t("mapping.fxYear", { min: PRICE_YEAR_RANGE[0], max: PRICE_YEAR_RANGE[1] });
  return errors;
}

/** The preview request's fx object, or null for a GBP mapping or an incomplete EUR one. */
export function fxRequest(draft: FxDraft): FxRequest | null {
  if (draft.currency !== "EUR" || Object.keys(fxErrors(draft)).length) return null;
  return { eur_per_gbp: Number(draft.eurPerGbp.trim()), fx_basis: draft.fxBasis, price_year: Number(draft.priceYear.trim()) };
}

/** The converted-column header note: "converted at {rate} EUR/GBP ({basis}, {year})". */
export function fxCaption(fx: { eur_per_gbp: number; fx_basis: string; price_year?: number | null }, t: Translate = ENGLISH): string {
  return t("mapping.converted", { rate: fx.eur_per_gbp, basis: fx.fx_basis, year: fx.price_year != null ? `, ${fx.price_year}` : "" });
}

/** Spec 11.6 (S-D5): a column whose name suggests euros while GBP is selected (a non-blocking hint). */
export const EUR_COLUMN_HINT = ENGLISH("mapping.eurHint");
export function columnSuggestsEur(columnName: string | null | undefined, currency: Currency): boolean {
  return currency === "GBP" && /eur|€/i.test(String(columnName ?? ""));
}

/** Spec 11.6 (S-D4): the optional timestamp declaration of a mapping preview request. */
export type TimestampDraft = { column: string; timeZone: string; dateOrder?: string };
export const EMPTY_TIMESTAMP: TimestampDraft = { column: "", timeZone: "UTC", dateOrder: "auto" };
export const TIME_ZONES = ["UTC", "Europe/London"] as const;
/** S-中3 (R4, A27): the order of numeric day/month dates such as 02/01/2025 (ISO dates are never reordered). */
export const DATE_ORDERS = [
  { value: "auto", label: "mapping.dateOrderAuto" },
  { value: "day_first", label: "mapping.dateOrderDayFirst" },
  { value: "month_first", label: "mapping.dateOrderMonthFirst" },
] as const satisfies readonly { value: string; label: MessageKey }[];
export function timestampRequest(draft: TimestampDraft): { column: string; time_zone: string; date_order: string } | null {
  return draft.column ? { column: draft.column, time_zone: draft.timeZone || "UTC", date_order: draft.dateOrder || "auto" } : null;
}

/** S-低2 / S-中3: the coverage line of the timestamp report ("365 days · data year 2025 · dates DD/MM/YYYY (detected …)"). */
export function timestampCoverageText(report: { coverage?: { span_days: number; data_years: number[] } | null; date_order?: string; date_order_basis?: string } | null | undefined, t: Translate = ENGLISH): string {
  if (!report) return "";
  const parts: string[] = [];
  if (report.coverage) {
    parts.push(t("mapping.coverageDays", { days: report.coverage.span_days }));
    if (report.coverage.data_years.length) parts.push(t("mapping.coverageYear", { years: report.coverage.data_years.join("–") }));
  }
  if (report.date_order && report.date_order !== "iso") {
    const order = report.date_order === "day_first" ? "DD/MM/YYYY" : "MM/DD/YYYY";
    parts.push(`${t("mapping.coverageOrder", { order })}${report.date_order_basis ? ` (${report.date_order_basis})` : ""}`);
  }
  return parts.join(" · ");
}

/** S-F-低6 (R5): a review's expiry in local time to the minute ("2026-10-07 23:05 local time"), not a raw ISO string.
 * A system time (spec 3): the reader's clock, not the UTC model clock. */
export function reviewExpiryText(iso: string, t: Translate = ENGLISH): string {
  const date = new Date(iso);
  if (!Number.isFinite(date.getTime())) return iso;
  const two = (value: number) => String(value).padStart(2, "0");
  return t("mapping.localTime", { time: `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())} ${two(date.getHours())}:${two(date.getMinutes())}` });
}
