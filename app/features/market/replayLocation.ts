// The replay window in the URL of /runs/[runId]/replay (P1 W3, spec 5.1).

/** P1 W3 (spec 5.1): the replayed window a link names, /runs/[runId]/replay?year=&period=&stage=
 * (and &from= when the window does not start at the selected period). */
export function linkedReplayWindow(search: string): { year: number; period: number; from: number; stage: string } | null {
  const params = new URLSearchParams(search);
  const number = (name: string) => { const value = params.get(name); return value != null && /^\d{1,6}$/.test(value) ? Number(value) : null; };
  const year = number("year");
  if (!year) return null;
  const period = number("period") ?? 0;
  return { year, period, from: number("from") ?? period, stage: params.get("stage") ?? "" };
}
