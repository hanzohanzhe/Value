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
// Intl.NumberFormat is used only in this file (frontend-guards test).

const formatters = new Map<string, Intl.NumberFormat>();

function numberFormat(options: Intl.NumberFormatOptions): Intl.NumberFormat {
  const key = JSON.stringify(options);
  let formatter = formatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat("en-GB", options);
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

const PRICE_LABELS: Record<PriceBasis, { label: string; suffix?: string; title?: string }> = {
  average_period_cost: { label: "Average period cost", suffix: "(£/MWh demand)", title: "Total period cost divided by demand. Not a marginal clearing price." },
  national_ahead_clearing_price: { label: "National ahead clearing price", title: "Uniform price set by the last accepted offer in the ahead stage." },
  balance_shadow_price: { label: "Balance shadow price", title: "Dual value of the energy-balance constraint." },
  ahead_settlement_price: { label: "Ahead settlement price" },
  not_declared: { label: "Price (basis not recorded)", title: "This ledger does not declare what the price represents." },
};

export function isPriceBasis(value: unknown): value is PriceBasis {
  return typeof value === "string" && (PRICE_BASES as readonly string[]).includes(value);
}

export type FormattedPrice = { value: string | null; label: string; title?: string };

/** Value and label of a period price; `aggregated` prefixes "Demand-weighted" for a multi-period window. */
export function formatPrice(gbpPerMwh: number | null | undefined, basis: unknown, options: { aggregated?: boolean } = {}): FormattedPrice {
  const known = isPriceBasis(basis) ? basis : "not_declared";
  const definition = PRICE_LABELS[known];
  let label = definition.suffix ? `${definition.label} ${definition.suffix}` : definition.label;
  if (options.aggregated) {
    label = known === "not_declared"
      ? "Demand-weighted price (basis not recorded)"
      : `Demand-weighted ${label.charAt(0).toLowerCase()}${label.slice(1)}`;
  }
  const number = formatNumber(gbpPerMwh, 2);
  return { value: number == null ? null : `£${number}/MWh`, label, title: definition.title };
}
