// S-中1 (four-role test, A27): one rule for every model time the UI shows.
// The model clock is UTC on a fixed 365-day year (gridform_core/model_clock.py):
// period p of model year Y starts at 00:00 UTC of model day floor(p / periods per
// day), 29 February is never a model day, and there is no daylight saving.

export const MODEL_CLOCK_LABEL = "UTC model time";

function isLeap(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

/** Milliseconds of the UTC start of `period` of model year `year` (the year's length gives its end). */
export function modelPeriodStartMs(year: number, period: number, periodHours = 0.5): number {
  const perDay = Math.round(24 / periodHours);
  const day = Math.floor(period / perDay);
  const offsetHours = (period - day * perDay) * periodHours;
  let start = Date.UTC(year, 0, 1) + day * 86_400_000;
  if (isLeap(year) && start >= Date.UTC(year, 1, 29)) start += 86_400_000;
  return start + offsetHours * 3_600_000;
}

/** "YYYY-MM-DD HH:MM" (UTC) of a model period. */
export function modelTimestamp(year: number, period: number, periodHours = 0.5): string {
  return new Date(modelPeriodStartMs(year, period, periodHours)).toISOString().slice(0, 16).replace("T", " ");
}

/** A backend model timestamp ("2025-07-01T16:00:00Z") as "2025-07-01 16:00"; other text is returned trimmed of "T". */
export function modelTimeText(value: string | null | undefined): string {
  if (!value) return "";
  const match = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})(?::\d{2}(?:\.\d+)?)?(?:Z|\+00:00)?$/.exec(value);
  return match ? `${match[1]} ${match[2]}` : value.replace("T", " ");
}

/** The label after a model time range: "(UTC model time)", or the ledger's own zone when it is not UTC. */
export function modelClockSuffix(timezone: string | null | undefined): string {
  if (!timezone) return "";
  return timezone === "UTC" ? ` (${MODEL_CLOCK_LABEL})` : ` (${timezone} model time)`;
}
