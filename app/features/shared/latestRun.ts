// Which Run is "the latest" (review F4-07, P1 spec 6.1).
//
// The workspace lists Runs by `updated_at`, newest first (backend/server.py
// `_list_json`), so "last in the list" is the oldest one and "first in the
// list" is the one touched last, not the one started last.  "Latest" means
// created last: `created_at` when recorded, otherwise the timestamp inside the
// Run ID (`…-YYYYMMDD-HHMMSS-<hex>`); Runs with neither keep their list order
// after the dated ones.  Every place that opens "the latest Run" uses this.

export type DatedRun = { id: string; project_id?: string; mode?: string; created_at?: string | null };

/** Milliseconds of the Run's creation, or null when nothing records it. */
export function runCreatedTime(run: DatedRun): number | null {
  const recorded = run.created_at ? Date.parse(run.created_at) : Number.NaN;
  if (Number.isFinite(recorded)) return recorded;
  const fromId = /-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-[0-9a-f]+$/.exec(run.id);
  if (!fromId) return null;
  const [, year, month, day, hour, minute, second] = fromId.map(Number);
  return Date.UTC(year, month - 1, day, hour, minute, second);
}

/** The Runs newest-created first (stable: undated Runs keep their list order, after dated ones). */
export function newestRuns<T extends DatedRun>(runs: readonly T[], count = runs.length): T[] {
  return runs
    .map((run, index) => ({ run, index, time: runCreatedTime(run) }))
    .sort((a, b) => {
      if (a.time !== null && b.time !== null && a.time !== b.time) return b.time - a.time;
      if (a.time === null && b.time !== null) return 1;
      if (a.time !== null && b.time === null) return -1;
      return a.index - b.index;
    })
    .slice(0, Math.max(0, count))
    .map((item) => item.run);
}

/** The latest Run of one Study (optionally of one scope), or undefined. */
export function latestRunFor<T extends DatedRun>(runs: readonly T[], projectId: string | undefined, mode?: string): T | undefined {
  if (!projectId) return undefined;
  return newestRuns(runs.filter((run) => run.project_id === projectId && (mode === undefined || run.mode === mode)), 1)[0];
}
