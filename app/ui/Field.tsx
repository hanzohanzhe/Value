"use client";
import { useId, useState, type ReactNode, type InputHTMLAttributes, type SelectHTMLAttributes } from "react";
import { checkNumber, numberText, type NumberCheck, type NumberRules } from "./numberField.ts";
import { useUiStrings } from "./useUiStrings.ts";
import "./Field.css";

type FieldFrame = { label: ReactNode; hint?: ReactNode; error?: ReactNode; className?: string; required?: boolean };

/** Spec 2: label, hint and error around one control; the control gets the
 * ids for aria-describedby and aria-invalid from `children(ids)`. */
export function Field({ label, hint, error, className, required, children }: FieldFrame & { children: (ids: { id: string; describedBy?: string; invalid: boolean }) => ReactNode }) {
  const id = useId();
  const hintId = hint != null ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return <div className={`v-field${error ? " v-field--invalid" : ""}${className ? ` ${className}` : ""}`}>
    <label className="v-field__label" htmlFor={id}>{label}{required && <span className="v-field__required" aria-hidden="true"> *</span>}</label>
    {children({ id, describedBy, invalid: Boolean(error) })}
    {hint != null && <p className="v-field__hint" id={hintId}>{hint}</p>}
    {error ? <p className="v-field__error" id={errorId}>{error}</p> : null}
  </div>;
}

export function TextField({ label, hint, error, className, required, value, onChange, ...rest }: FieldFrame & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "className"> & { value: string; onChange: (value: string) => void }) {
  return <Field label={label} hint={hint} error={error} className={className} required={required}>{({ id, describedBy, invalid }) =>
    <input {...rest} id={id} className="v-input" value={value} required={required} aria-describedby={describedBy} aria-invalid={invalid || undefined} onChange={(event) => onChange(event.target.value)} />}
  </Field>;
}

export type SelectOption = { value: string; label: ReactNode; disabled?: boolean };

export function Select({ label, hint, error, className, required, value, onChange, options, ...rest }: FieldFrame & Omit<SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange" | "className"> & { value: string; onChange: (value: string) => void; options: readonly SelectOption[] }) {
  return <Field label={label} hint={hint} error={error} className={className} required={required}>{({ id, describedBy, invalid }) =>
    <select {...rest} id={id} className="v-input v-select" value={value} required={required} aria-describedby={describedBy} aria-invalid={invalid || undefined} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => <option key={option.value} value={option.value} disabled={option.disabled}>{option.label}</option>)}
    </select>}
  </Field>;
}

/** Spec 2 / F4-02: clearing the box gives null (not 0); min, max and step are
 * checked as the user types and the message shows at once; `onChange` gets the
 * check so the owner can block saving while `valid` is false. */
export function NumberField({ label, hint, error, className, required, value, onChange, min, max, step, unit, ...rest }: FieldFrame & NumberRules & Omit<InputHTMLAttributes<HTMLInputElement>, "value" | "onChange" | "className" | "min" | "max" | "step" | "type"> & {
  value: number | null;
  onChange: (value: number | null, check: NumberCheck) => void;
  unit?: string;
}) {
  const strings = useUiStrings();
  const [text, setText] = useState(() => numberText(value));
  const [lastValue, setLastValue] = useState(value);
  // A new value from outside (reset, load) replaces the text; typing does not loop.
  // Only a change of the `value` prop counts: an owner that keeps its last valid
  // number while the box is empty or out of range (P1 W4a) leaves the typed text
  // and its message in place, so the error stays visible instead of snapping back.
  if (value !== lastValue) {
    setLastValue(value);
    if (checkNumber(text, { min, max, step }).value !== value) setText(numberText(value));
  }
  const check = checkNumber(text, { min, max, step, required }, strings);
  const message = error ?? check.message;
  return <Field label={label} hint={hint} error={message} className={className} required={required}>{({ id, describedBy, invalid }) =>
    <span className="v-number">
      <input
        {...rest}
        id={id}
        className="v-input v-number__input"
        type="text"
        inputMode="decimal"
        autoComplete="off"
        value={text}
        required={required}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        onChange={(event) => {
          const next = event.target.value;
          setText(next);
          const result = checkNumber(next, { min, max, step, required }, strings);
          onChange(result.value, result);
        }}
      />
      {unit && <span className="v-number__unit">{unit}</span>}
    </span>}
  </Field>;
}
