// Default wording of the shared components (spec 2). One place, so the i18n
// dictionaries (spec 3, W2/W5) can supply these keys; every component also
// takes the text as a prop.
export const UI_STRINGS = {
  loading: "Loading",
  working: "Working",
  close: "Close",
  cancel: "Cancel",
  confirm: "Confirm",
  copy: "Copy",
  copied: "Copied",
  copyFailed: "Copy failed",
  copyFullValue: "Copy full value",
  dismiss: "Dismiss",
  showDataTable: "Show data table",
  hideDataTable: "Hide data table",
  chooseFile: "Choose a file or drop it here",
  noFileChosen: "No file chosen",
  scrollTable: "Scrollable table",
  numberRequired: "Enter a number",
  numberNotNumeric: "Not a number",
  numberBelowMin: "Must be at least {min}",
  numberAboveMax: "Must be at most {max}",
  numberStep: "Must be a multiple of {step}",
  steps: "Steps",
} as const;

export type UiStringKey = keyof typeof UI_STRINGS;

/** Replace {name} placeholders with values. */
export function fill(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (all, name: string) => (name in values ? String(values[name]) : all));
}
