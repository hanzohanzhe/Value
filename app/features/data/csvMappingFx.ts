// F-P05A-1 (designer ruling 2026-10-06): the currency and EUR->GBP rate of a
// price-column mapping (P0-5a S10 backend: gridform_core/data_adapters.py,
// backend/data_mapping.py). Pure logic: the rate is declared by the user, never
// defaulted; the backend performs the conversion and reports both values.
import type { CsvMappingRole } from "./csvMappingTypes.ts";

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
export function fxErrors(draft: FxDraft): FxErrors {
  if (draft.currency !== "EUR") return {};
  const errors: FxErrors = {};
  const rate = draft.eurPerGbp.trim();
  if (!/^\d+(\.\d{1,4})?$/.test(rate) || !(Number(rate) > 0)) errors.eurPerGbp = "GF_MAPPING_FX：EUR per GBP 必须是大于 0 的数，最多 4 位小数。";
  if (!(FX_BASES as readonly string[]).includes(draft.fxBasis)) errors.fxBasis = "GF_MAPPING_FX：请选择汇率口径（FX basis）。";
  const year = draft.priceYear.trim();
  if (!/^\d{4}$/.test(year) || Number(year) < PRICE_YEAR_RANGE[0] || Number(year) > PRICE_YEAR_RANGE[1]) errors.priceYear = `GF_MAPPING_FX：价格年份须为 ${PRICE_YEAR_RANGE[0]}–${PRICE_YEAR_RANGE[1]} 之间的整数。`;
  return errors;
}

/** The preview request's fx object, or null for a GBP mapping or an incomplete EUR one. */
export function fxRequest(draft: FxDraft): FxRequest | null {
  if (draft.currency !== "EUR" || Object.keys(fxErrors(draft)).length) return null;
  return { eur_per_gbp: Number(draft.eurPerGbp.trim()), fx_basis: draft.fxBasis, price_year: Number(draft.priceYear.trim()) };
}

/** The converted-column header note: "converted at {rate} EUR/GBP ({basis}, {year})". */
export function fxCaption(fx: { eur_per_gbp: number; fx_basis: string; price_year?: number | null }): string {
  return `converted at ${fx.eur_per_gbp} EUR/GBP (${fx.fx_basis}${fx.price_year != null ? `, ${fx.price_year}` : ""})`;
}
