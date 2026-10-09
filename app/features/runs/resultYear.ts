// The year shown on a Run's annual results page (/runs/[runId]?year=, P1 spec 5.1/6.5).

/** The ?year= of a results URL when the Run has that year, else the latest year; null without years. */
export function resultYearFromSearch(search: string, years: readonly number[]): number | null {
  if (!years.length) return null;
  const raw = new URLSearchParams(search).get("year");
  const asked = raw != null && /^\d{4}$/.test(raw) ? Number(raw) : null;
  return asked != null && years.includes(asked) ? asked : Math.max(...years);
}
