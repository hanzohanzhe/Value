// F4-05 (P1 W4b, spec 6.3): following a Data Workbench job with the existing
// API only (GET /jobs/{id}). Pure helpers; DataWorkbench.tsx does the I/O.
//
//   * Polling: every 650 ms while the job answers; after a failed read the
//     next attempt waits longer (1.3, 2.6, 5.2, 10 s) and after five failures
//     in a row polling stops with a "Check the job again" button, instead of
//     stopping silently after the first error.
//   * After a reload: the backend has no "list active jobs" route, so the id
//     of the job this browser started is kept in localStorage (wrapped in
//     try/catch; without storage the page still works, it only cannot resume).
//   * Progress: the backend reports a fraction and timestamps; the strip shows
//     the percentage and the elapsed time.
import type { DataJob } from "./types";

export const TERMINAL_JOB_STATUSES: ReadonlySet<string> = new Set(["completed", "failed", "cancelled"]);
export const POLL_INTERVAL_MS = 650;
export const MAX_POLL_FAILURES = 5;
export const ACTIVE_JOB_STORAGE_KEY = "value.dataWorkbench.activeJob";

export function isActiveJob(job: Pick<DataJob, "status"> | null | undefined): boolean {
  return Boolean(job && !TERMINAL_JOB_STATUSES.has(job.status));
}

/** Milliseconds before the next status read: 650 ms normally; 1.3, 2.6, 5.2 then 10 s after 1, 2, 3, 4+ failures. */
export function pollDelay(failures: number): number {
  if (failures <= 0) return POLL_INTERVAL_MS;
  return Math.min(10_000, POLL_INTERVAL_MS * 2 ** failures);
}

/** Whole percent of a job's progress fraction (clamped; missing = 0). */
export function progressPercent(progress: unknown): number {
  const value = typeof progress === "number" && Number.isFinite(progress) ? progress : 0;
  return Math.round(Math.min(1, Math.max(0, value)) * 100);
}

/** Seconds from the job's creation to its last update (or to `now` while it runs); null without a creation time. */
export function elapsedSeconds(job: Pick<DataJob, "status" | "created_at" | "updated_at">, now: number): number | null {
  const start = Date.parse(job.created_at ?? "");
  if (!Number.isFinite(start)) return null;
  const end = isActiveJob(job) ? now : Date.parse(job.updated_at ?? "");
  return Math.max(0, Math.round(((Number.isFinite(end) ? end : now) - start) / 1000));
}

/** The job id this browser was following, or null (no storage, nothing stored, or not an id). */
export function readTrackedJob(storage: Pick<Storage, "getItem"> | null | undefined): string | null {
  try {
    const value = storage?.getItem(ACTIVE_JOB_STORAGE_KEY) ?? null;
    return value && /^[A-Za-z0-9._:-]{1,200}$/.test(value) ? value : null;
  } catch {
    return null;
  }
}

/** Remember (or with null forget) the followed job; storage errors are ignored. */
export function writeTrackedJob(storage: Pick<Storage, "setItem" | "removeItem"> | null | undefined, jobId: string | null): void {
  try {
    if (jobId) storage?.setItem(ACTIVE_JOB_STORAGE_KEY, jobId);
    else storage?.removeItem(ACTIVE_JOB_STORAGE_KEY);
  } catch {
    /* blocked storage: the page works, it only cannot resume after a reload */
  }
}

/** window.localStorage when it can be read at all. */
export function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null;
  }
}
