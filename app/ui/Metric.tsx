import type { ReactNode } from "react";
import { formatNumber, withUnit, type NumberOptions } from "../features/shared/format.ts";
import type { ValueStateKey } from "../features/shared/valueStates.ts";
import { StatusWord } from "./StatusWord.tsx";
import "./Metric.css";

/** Spec 2: value, unit and a basis note. A null, missing or non-finite value
 * shows its state word (default "Not recorded"), never 0. */
export function Metric({ label, value, unit = "", basis, missingState = "not_recorded", missingTitle, digits, formatted, className }: {
  label: ReactNode;
  value: number | null | undefined;
  unit?: string;
  /** The basis or scope note under the value, e.g. "PSM boundary · 2025". */
  basis?: ReactNode;
  missingState?: ValueStateKey;
  missingTitle?: string;
  digits?: NumberOptions | number;
  /** A value already formatted by format.ts (e.g. formatEnergy); overrides digits. */
  formatted?: string | null;
  className?: string;
}) {
  const text = typeof value === "number" && Number.isFinite(value) ? (formatted !== undefined ? formatted : formatNumber(value, digits ?? 2)) : null;
  return <div className={`v-metric${className ? ` ${className}` : ""}`}>
    <span className="v-metric__label">{label}</span>
    <span className="v-metric__value">{text == null
      ? <StatusWord state={missingState} title={missingTitle} />
      : withUnit(text, unit)}</span>
    {basis != null && <span className="v-metric__basis">{basis}</span>}
  </div>;
}
