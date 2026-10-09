import { UI_STRINGS, fill } from "./strings.ts";

export type NumberRules = { min?: number; max?: number; step?: number; required?: boolean };
export type NumberCheck = { value: number | null; valid: boolean; message: string | null };

/** Parse the text of a number box (spec 2 / F4-02): empty is null, never 0;
 * out-of-range and non-numeric text is invalid with a message, so the form
 * can block saving. Accepts a leading minus, decimals and exponents. */
export function checkNumber(text: string, rules: NumberRules = {}, strings: Record<"numberRequired" | "numberNotNumeric" | "numberBelowMin" | "numberAboveMax" | "numberStep", string> = UI_STRINGS): NumberCheck {
  const trimmed = text.trim();
  if (trimmed === "") return { value: null, valid: !rules.required, message: rules.required ? strings.numberRequired : null };
  if (!/^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$/i.test(trimmed)) return { value: null, valid: false, message: strings.numberNotNumeric };
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return { value: null, valid: false, message: strings.numberNotNumeric };
  if (rules.min != null && value < rules.min) return { value, valid: false, message: fill(strings.numberBelowMin, { min: rules.min }) };
  if (rules.max != null && value > rules.max) return { value, valid: false, message: fill(strings.numberAboveMax, { max: rules.max }) };
  if (rules.step != null && rules.step > 0) {
    const base = rules.min ?? 0;
    const ratio = (value - base) / rules.step;
    if (Math.abs(ratio - Math.round(ratio)) > 1e-9 * Math.max(1, Math.abs(ratio))) return { value, valid: false, message: fill(strings.numberStep, { step: rules.step }) };
  }
  return { value, valid: true, message: null };
}

/** Text for a number box from a stored value; null shows as empty, not "0". */
export function numberText(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "";
}
