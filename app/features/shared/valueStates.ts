// The one vocabulary for "this slot has no true value" (P0 frontend spec 1.1).
//
// A number on a result view is either the recorded value with its basis, or one
// of these state words. Components take the text from here and never write
// their own "0", "N/A" or empty string for a missing quantity.

export type ValueStateKey =
  | "missing"
  | "not_recorded"
  | "not_modelled"
  | "not_evaluated"
  | "not_computed"
  | "partial_year"
  | "non_annual"
  | "in_progress"
  | "stopped"
  | "unavailable"
  | "invalid"
  | "withheld"
  | "basis_not_recorded";

/** muted: neutral grey text; amber: needs attention; red: invalid; blue: neutral information. */
export type ValueStateTone = "muted" | "amber" | "red" | "blue";

export type ValueStateDefinition = { text: string; tone: ValueStateTone };

export const VALUE_STATES: Readonly<Record<ValueStateKey, ValueStateDefinition>> = {
  missing: { text: "—", tone: "muted" },
  not_recorded: { text: "Not recorded", tone: "muted" },
  not_modelled: { text: "Not modelled", tone: "muted" },
  not_evaluated: { text: "Not evaluated", tone: "muted" },
  not_computed: { text: "Not computed", tone: "muted" },
  partial_year: { text: "Partial year · {coverage}%", tone: "amber" },
  non_annual: { text: "Non-annual run", tone: "amber" },
  in_progress: { text: "Running", tone: "blue" },
  // Designer ruling 2 (M2 UI review): a cancelled or stopped Run's coverage; "Withheld" is only Q14.
  stopped: { text: "Stopped · {coverage}%", tone: "amber" },
  unavailable: { text: "Unavailable", tone: "muted" },
  invalid: { text: "Invalid", tone: "red" },
  withheld: { text: "Withheld", tone: "amber" },
  basis_not_recorded: { text: "basis not recorded", tone: "muted" },
};

export function isValueStateKey(value: unknown): value is ValueStateKey {
  return typeof value === "string" && Object.hasOwn(VALUE_STATES, value);
}

/** Display text of a state word; `partial_year` and `stopped` need the coverage percentage. */
export function valueStateText(key: ValueStateKey, coveragePercent?: number | null): string {
  const text = VALUE_STATES[key].text;
  if (key !== "partial_year" && key !== "stopped") return text;
  const coverage = typeof coveragePercent === "number" && Number.isFinite(coveragePercent)
    ? String(Math.round(coveragePercent * 10) / 10)
    : "?";
  return text.replace("{coverage}", coverage);
}

export function valueStateTone(key: ValueStateKey): ValueStateTone {
  return VALUE_STATES[key].tone;
}
