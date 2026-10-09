// The single number-formatting layer of the VALUE frontend (P0-9 S1, spec 1.2).
//
// Rules every function here keeps:
//   * a missing or non-finite value returns null; the caller renders a state
//     word from valueStates.ts. Nothing here turns a missing value into 0;
//   * no negative zero;
//   * a non-zero value is never rounded to "0": below the display precision
//     it is shown as "<0.01" / ">-0.01" (or with significant digits);
//   * money and energy round first and choose the unit afterwards, so
//     999,999.9 is £1.00m, never £1,000k.
// Intl.NumberFormat and Intl.DateTimeFormat are used only in this file
// (frontend-guards test). They follow the interface language (P1 spec 3):
// LocaleProvider calls setFormatLocale; model time stays UTC (S-中1).

import { tr, type MessageKey } from "../../i18n/index.ts";

const DEFAULT_FORMAT_LOCALE = "en-GB";
let formatLocale = DEFAULT_FORMAT_LOCALE;

/** The Intl locale for numbers and dates ("en-GB" or "zh-CN"); set by the interface language. */
export function setFormatLocale(tag: string): void {
  formatLocale = tag || DEFAULT_FORMAT_LOCALE;
}

export function getFormatLocale(): string {
  return formatLocale;
}

const formatters = new Map<string, Intl.NumberFormat>();

function numberFormat(options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = `${formatLocale}|${JSON.stringify(options)}`;
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat(formatLocale, options);
    formatters.set(key, formatter);
  }
  return formatter;
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function withoutNegativeZero(text: string): string {
  return /^-0([.,]0*)?$/.test(text) ? text.slice(1) : text;
}

export type NumberOptions = {
  /** Maximum fraction digits (default 2). */
  digits?: number;
  /** Minimum fraction digits (default 0). */
  minimumDigits?: number;
};

/**
 * Spec principle 1: a slot shows a value with its unit, or the state word on
 * its own. Takes an already formatted number (null or "—" when missing) and
 * appends the unit only to a value: never "— MWh" or "£—/MWh".
 */
export function withUnit(formatted: string | null | undefined, unit: string, separator = " ", prefix = ""): string {
  if (formatted == null || formatted === "—") return "—";
  return `${prefix}${formatted}${unit ? `${separator}${unit}` : ""}`;
}

/** A plain number, or null when the value is missing. */
export function formatNumber(value: number | null | undefined, options: NumberOptions | number = {}): string | null {
  if (!finite(value)) return null;
  const digits = typeof options === "number" ? options : options.digits ?? 2;
  const minimumDigits = typeof options === "number" ? 0 : Math.min(options.minimumDigits ?? 0, digits);
  if (value === 0) return minimumDigits ? numberFormat({ minimumFractionDigits: minimumDigits, maximumFractionDigits: digits }).format(0) : "0";
  const precision = 10 ** -digits;
  if (Math.abs(value) < precision) {
    const smallest = numberFormat({ maximumFractionDigits: digits }).format(precision);
    return value > 0 ? `<${smallest}` : `>-${smallest}`;
  }
  return withoutNegativeZero(numberFormat({ minimumFractionDigits: minimumDigits, maximumFractionDigits: digits }).format(value));
}

/** Significant-digit quantity; very small non-zero values use scientific notation (2.01e-4). */
export function formatQuantity(value: number | null | undefined, significant = 3): string | null {
  if (!finite(value)) return null;
  if (value === 0) return "0";
  if (Math.abs(value) < 1e-3) {
    const [mantissa, exponent] = value.toExponential(Math.max(significant - 1, 0)).split("e");
    const trimmed = mantissa.includes(".") ? mantissa.replace(/0+$/, "").replace(/\.$/, "") : mantissa;
    return `${trimmed}e${Number(exponent)}`;
  }
  return withoutNegativeZero(numberFormat({ maximumSignificantDigits: significant }).format(value));
}

/** Round to `significant` digits (for unit choice after rounding). */
function roundSignificant(value: number, significant: number): number {
  if (value === 0) return 0;
  return Number(value.toPrecision(significant));
}

// ---------------------------------------------------------------- energy / power

export type EnergyUnit = "kWh" | "MWh" | "GWh" | "TWh";
const ENERGY_FACTORS: Record<EnergyUnit, number> = { kWh: 1e-3, MWh: 1, GWh: 1e3, TWh: 1e6 };
const ENERGY_ORDER: EnergyUnit[] = ["kWh", "MWh", "GWh", "TWh"];

/** The unit for a magnitude in MWh: < 1 kWh-range, < 1e3 MWh, < 1e6 GWh, else TWh (after 3-significant-digit rounding). */
export function energyUnitFor(maximumAbsoluteMwh: number | null | undefined): EnergyUnit {
  if (!finite(maximumAbsoluteMwh) || maximumAbsoluteMwh === 0) return "MWh";
  const magnitude = Math.abs(maximumAbsoluteMwh);
  let unit: EnergyUnit = magnitude < 1 ? "kWh" : magnitude < 1e3 ? "MWh" : magnitude < 1e6 ? "GWh" : "TWh";
  // Round first, then promote: 999.6 MWh is 1 GWh, not "1,000 MWh".
  while (unit !== "TWh" && Math.abs(roundSignificant(magnitude / ENERGY_FACTORS[unit], 3)) >= 1000) {
    unit = ENERGY_ORDER[ENERGY_ORDER.indexOf(unit) + 1];
  }
  return unit;
}

export function formatEnergyIn(mwh: number | null | undefined, unit: EnergyUnit): string | null {
  if (!finite(mwh)) return null;
  const text = formatQuantity(mwh / ENERGY_FACTORS[unit], 3);
  return text == null ? null : `${text} ${unit}`;
}

/** An energy in MWh with a unit chosen from its own magnitude, 3 significant digits. */
export function formatEnergy(mwh: number | null | undefined): string | null {
  return finite(mwh) ? formatEnergyIn(mwh, energyUnitFor(Math.abs(mwh))) : null;
}

/** One unit for a whole table or KPI group: the unit of the group's largest magnitude. */
export function formatEnergyGroup(values: readonly (number | null | undefined)[]): { unit: EnergyUnit; format: (mwh: number | null | undefined) => string | null } {
  const magnitudes = values.filter(finite).map((value) => Math.abs(value));
  const unit = energyUnitFor(magnitudes.length ? Math.max(...magnitudes) : 0);
  return { unit, format: (mwh) => formatEnergyIn(mwh, unit) };
}

export type PowerUnit = "MW" | "GW";

export function powerUnitFor(maximumAbsoluteMw: number | null | undefined): PowerUnit {
  if (!finite(maximumAbsoluteMw)) return "MW";
  return Math.abs(roundSignificant(Math.abs(maximumAbsoluteMw), 3)) >= 1000 ? "GW" : "MW";
}

export function formatPowerIn(mw: number | null | undefined, unit: PowerUnit): string | null {
  if (!finite(mw)) return null;
  const text = formatQuantity(unit === "GW" ? mw / 1000 : mw, 3);
  return text == null ? null : `${text} ${unit}`;
}

export function formatPower(mw: number | null | undefined): string | null {
  return finite(mw) ? formatPowerIn(mw, powerUnitFor(mw)) : null;
}

export function formatPowerGroup(values: readonly (number | null | undefined)[]): { unit: PowerUnit; format: (mw: number | null | undefined) => string | null } {
  const magnitudes = values.filter(finite).map((value) => Math.abs(value));
  const unit = powerUnitFor(magnitudes.length ? Math.max(...magnitudes) : 0);
  return { unit, format: (mw) => formatPowerIn(mw, unit) };
}

// ------------------------------------------------------------------------ money

const MONEY_SCALES: [number, string][] = [[1e3, "k"], [1e6, "m"], [1e9, "bn"]];

/** £ with k / m / bn; rounded to the target precision before the unit is chosen. */
export function formatMoney(gbp: number | null | undefined): string | null {
  if (!finite(gbp)) return null;
  const sign = gbp < 0 ? "-" : "";
  const magnitude = Math.abs(gbp);
  if (Math.round(magnitude * 100) / 100 < 1000) {
    const text = formatNumber(magnitude, 2)!;
    // Below a penny: "<£0.01" / "-<£0.01" rather than "£0".
    if (text.startsWith("<")) return gbp < 0 ? `>-£${text.slice(1)}` : `<£${text.slice(1)}`;
    return text === "0" ? "£0" : `${sign}£${text}`;
  }
  for (let index = 0; index < MONEY_SCALES.length; index += 1) {
    const [factor, suffix] = MONEY_SCALES[index];
    const rounded = Math.round((magnitude / factor) * 1000) / 1000;
    if (rounded < 1000 || index === MONEY_SCALES.length - 1) {
      return `${sign}£${numberFormat({ minimumFractionDigits: 2, maximumFractionDigits: 3 }).format(rounded)}${suffix}`;
    }
  }
  return null;
}

// ------------------------------------------------------------------------ price

/** What a period price represents (backend `price_basis`, Q6). */
export type PriceBasis =
  | "average_period_cost"
  | "national_ahead_clearing_price"
  | "balance_shadow_price"
  | "ahead_settlement_price"
  | "not_declared";

export const PRICE_BASES: readonly PriceBasis[] = [
  "average_period_cost", "national_ahead_clearing_price", "balance_shadow_price", "ahead_settlement_price", "not_declared",
];

// P1 W5: dictionary messages (price.*) in the interface language.
const PRICE_LABELS: Record<PriceBasis, { label: MessageKey; suffix?: MessageKey; title?: MessageKey }> = {
  average_period_cost: { label: "price.average_period_cost", suffix: "price.average_period_cost.suffix", title: "price.average_period_cost.title" },
  national_ahead_clearing_price: { label: "price.national_ahead_clearing_price", title: "price.national_ahead_clearing_price.title" },
  balance_shadow_price: { label: "price.balance_shadow_price", title: "price.balance_shadow_price.title" },
  ahead_settlement_price: { label: "price.ahead_settlement_price" },
  not_declared: { label: "price.not_declared", title: "price.not_declared.title" },
};

export function isPriceBasis(value: unknown): value is PriceBasis {
  return typeof value === "string" && (PRICE_BASES as readonly string[]).includes(value);
}

export type FormattedPrice = { value: string | null; label: string; title?: string };

/** Value and label of a period price; `aggregated` prefixes "Demand-weighted" for a multi-period window. */
export function formatPrice(gbpPerMwh: number | null | undefined, basis: unknown, options: { aggregated?: boolean } = {}): FormattedPrice {
  const known = isPriceBasis(basis) ? basis : "not_declared";
  const definition = PRICE_LABELS[known];
  let label = definition.suffix ? tr("price.withSuffix", { label: tr(definition.label), suffix: tr(definition.suffix) }) : tr(definition.label);
  if (options.aggregated) {
    label = known === "not_declared"
      ? tr("price.weightedNotDeclared")
      : tr("price.weighted", { label: `${label.charAt(0).toLowerCase()}${label.slice(1)}` });
  }
  const number = formatNumber(gbpPerMwh, 2);
  return { value: number == null ? null : `£${number}/MWh`, label, title: definition.title ? tr(definition.title) : undefined };
}

// ------------------------------------------------------------------ date / time

const dateFormatters = new Map<string, Intl.DateTimeFormat>();

function dateFormat(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = `${formatLocale}|${JSON.stringify(options)}`;
  let formatter = dateFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(formatLocale, options);
    dateFormatters.set(key, formatter);
  }
  return formatter;
}

function instant(value: string | number | Date | null | undefined): Date | null {
  if (value == null || value === "") return null;
  const date = value instanceof Date ? value : new Date(value);
  return Number.isFinite(date.getTime()) ? date : null;
}

/**
 * A system time (review expiry, file or Run creation time) in the reader's
 * own time zone and interface language, or null when missing or unreadable.
 * Model time never goes through here: it is UTC (formatModelInstant).
 */
export function formatSystemTime(value: string | number | Date | null | undefined): string | null {
  const date = instant(value);
  return date ? dateFormat({ dateStyle: "medium", timeStyle: "short" }).format(date) : null;
}

/** A model instant as "YYYY-MM-DD HH:MM UTC", never converted to local time (S-中1, spec 6.5). */
export function formatModelInstant(value: string | number | Date | null | undefined): string | null {
  const date = instant(value);
  if (!date) return null;
  const parts = Object.fromEntries(new Intl.DateTimeFormat("en-GB", {
    timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date).map((part) => [part.type, part.value]));
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute} UTC`;
}
