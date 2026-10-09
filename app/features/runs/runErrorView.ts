// A failed Run's error as the Run centre shows it (P1 spec 6.5): the error code
// and the first line of the diagnostic; the rest on request. Pure view logic.

export type RunErrorFields = { error?: string | null; error_code?: string | null; error_detail?: string | null };

/** The first non-empty line of a diagnostic text, trimmed; "" when there is none. */
export function firstLine(text: string | null | undefined): string {
  return String(text ?? "").split(/\r?\n/).map((line) => line.trim()).find(Boolean) ?? "";
}

/**
 * The error of a Run: its code, the first diagnostic line and whatever else was
 * recorded (more lines of the message, the detail). Null when the Run records
 * no error.
 */
export function runErrorSummary(run: RunErrorFields | null | undefined): { code: string; headline: string; rest: string } | null {
  if (!run || (!run.error && !run.error_code)) return null;
  const message = String(run.error ?? "").trim();
  const headline = firstLine(message);
  const remainder = message.split(/\r?\n/).map((line) => line.trimEnd());
  const index = remainder.findIndex((line) => line.trim() === headline);
  const more = index >= 0 ? remainder.slice(index + 1).join("\n").trim() : "";
  const detail = String(run.error_detail ?? "").trim();
  const rest = [more, detail && detail !== headline ? detail : ""].filter(Boolean).join("\n");
  return { code: String(run.error_code ?? ""), headline, rest };
}
