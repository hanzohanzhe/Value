// Polling for the VALUE frontend (P1 spec 4, P0-3 S8).
//
//   * one request in flight at a time; a manual refresh during a poll waits
//     for it and then reads again (never a stale answer for a fresh action);
//   * paused while the document is hidden, refreshed at once when it is shown;
//   * after a failure: 2, 4, 8, 16, then 30 s; offline after 3 failures;
//   * structural sharing: data equal to the previous answer keeps the previous
//     object references (objects in arrays are matched by ID), so effects that
//     depend on them do not fire again on every poll and selections stay (F1-01).

/** Consecutive failures before the rail says "Backend offline" (spec 4). */
export const OFFLINE_AFTER_FAILURES = 3;
export const POLL_BASE_MS = 2_000;
export const POLL_MAX_MS = 30_000;

/** Polling interval after `failures` consecutive failures: 2 s doubling to at most 30 s. */
export function pollDelay(failures: number): number {
  return Math.min(POLL_MAX_MS, POLL_BASE_MS * 2 ** Math.max(0, failures));
}

export type ServiceState = "loading" | "online" | "degraded" | "offline";

/** Service state from the last health status and the consecutive refresh failures. */
export function serviceState(failures: number, healthStatus: string | null | undefined, loaded: boolean): ServiceState {
  if (failures >= OFFLINE_AFTER_FAILURES) return "offline";
  if (failures > 0 || healthStatus === "degraded") return "degraded";
  return loaded ? "online" : "loading";
}

// ------------------------------------------------------------ structural sharing

/** Keys that identify an object inside an array, in order of preference. */
export const IDENTITY_KEYS = ["id", "trash_id", "run_id", "extension_id", "module_id", "pack_id", "key"] as const;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false;
  const prototype = Object.getPrototypeOf(value);
  return prototype === Object.prototype || prototype === null;
}

function identityOf(value: unknown): string | null {
  if (!isPlainObject(value)) return null;
  for (const key of IDENTITY_KEYS) {
    const id = value[key];
    if (typeof id === "string" || typeof id === "number") return `${key}:${id}`;
  }
  return null;
}

function shareArray(previous: readonly unknown[], next: readonly unknown[]): unknown[] | readonly unknown[] {
  const byIdentity = new Map<string, unknown>();
  let duplicate = false;
  for (const item of previous) {
    const id = identityOf(item);
    if (id === null) continue;
    if (byIdentity.has(id)) duplicate = true;
    byIdentity.set(id, item);
  }
  let same = previous.length === next.length;
  const result = next.map((item, index) => {
    const id = identityOf(item);
    // Match by ID when IDs are unique; otherwise by position.
    const counterpart = id !== null && !duplicate ? byIdentity.get(id) : previous[index];
    const shared = counterpart === undefined ? item : replaceEqualDeep(counterpart, item);
    if (shared !== previous[index]) same = false;
    return shared;
  });
  return same ? previous : result;
}

/**
 * `next` with every part that is deeply equal to the corresponding part of
 * `previous` replaced by the previous object.  Returns `previous` itself when
 * nothing changed.  Only plain objects and arrays are shared; other values are
 * compared with Object.is.
 */
export function replaceEqualDeep<T>(previous: unknown, next: T): T {
  if (Object.is(previous, next)) return previous as T;
  if (Array.isArray(previous) && Array.isArray(next)) return shareArray(previous, next) as T;
  if (!isPlainObject(previous) || !isPlainObject(next)) return next;
  const previousKeys = Object.keys(previous);
  const nextKeys = Object.keys(next);
  let same = previousKeys.length === nextKeys.length;
  const result: Record<string, unknown> = {};
  for (const key of nextKeys) {
    const shared = key in previous ? replaceEqualDeep(previous[key], next[key]) : next[key];
    result[key] = shared;
    if (!(key in previous) || shared !== previous[key]) same = false;
  }
  return (same ? previous : result) as T;
}

// --------------------------------------------------------------------- poller

export type PollerState = {
  /** Consecutive failed reads (reset by a success). */
  failures: number;
  /** True while a read is in flight. */
  inFlight: boolean;
};

export type PollerOptions<T> = {
  /** One read.  Rejecting counts as a failure. */
  read: (signal: AbortSignal) => Promise<T>;
  /** Called with each successful answer. */
  onData: (data: T) => void;
  /** Called after each failed read with the error and the new failure count. */
  onError?: (error: unknown, failures: number) => void;
  /** An error after which polling stops and the failure is not counted (for example "open VALUE from its launcher"). */
  fatal?: (error: unknown) => boolean;
  /** Whether periodic reads should run now (for example while a Run is active).  Failures always poll with backoff. */
  shouldPoll?: () => boolean;
  /** Milliseconds before the next read after `failures` consecutive failures (default pollDelay).
   * R-9 (P1-polish): the in-page job pollers keep their own cadence and share the rest. */
  interval?: (failures: number) => number;
  /** Test seams. */
  setTimer?: (callback: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
  documentRef?: Pick<Document, "hidden" | "addEventListener" | "removeEventListener"> | null;
};

export type Poller<T> = {
  /** Read now (or right after the read in flight) and resolve with the answer, or null on failure. */
  refresh: () => Promise<T | null>;
  /** Re-evaluate the schedule (call when shouldPoll may have changed). */
  reschedule: () => void;
  /** Start periodic reads and the visibility listener. */
  start: () => void;
  /** Stop timers, listeners and the read in flight. */
  stop: () => void;
  state: () => PollerState;
};

export function createPoller<T>(options: PollerOptions<T>): Poller<T> {
  const setTimer = options.setTimer ?? ((callback: () => void, ms: number) => setTimeout(callback, ms));
  const clearTimer = options.clearTimer ?? ((handle: unknown) => clearTimeout(handle as ReturnType<typeof setTimeout>));
  const doc = options.documentRef === undefined ? (typeof document === "undefined" ? null : document) : options.documentRef;
  let failures = 0;
  let timer: unknown = null;
  let running = false;
  let inFlight: Promise<T | null> | null = null;
  let queued: Promise<T | null> | null = null;
  let controller: AbortController | null = null;

  const hidden = () => Boolean(doc?.hidden);

  function cancelTimer() {
    if (timer !== null) { clearTimer(timer); timer = null; }
  }

  function schedule() {
    cancelTimer();
    if (!running || hidden() || inFlight) return;
    if (failures === 0 && !(options.shouldPoll?.() ?? true)) return;
    timer = setTimer(() => { timer = null; void refresh(); }, (options.interval ?? pollDelay)(failures));
  }

  function readOnce(): Promise<T | null> {
    controller = new AbortController();
    const signal = controller.signal;
    const current = (async () => {
      try {
        const data = await options.read(signal);
        if (signal.aborted) return null;
        failures = 0;
        options.onData(data);
        return data;
      } catch (error) {
        if (signal.aborted) return null;
        if (options.fatal?.(error)) {
          running = false;
          cancelTimer();
          options.onError?.(error, failures);
          return null;
        }
        failures += 1;
        options.onError?.(error, failures);
        return null;
      }
    })();
    inFlight = current;
    void current.finally(() => {
      if (inFlight === current) inFlight = null;
      if (!queued) schedule();
    });
    return current;
  }

  function refresh(): Promise<T | null> {
    cancelTimer();
    if (!inFlight) return readOnce();
    // One more read after the one in flight; concurrent callers share it.
    queued ??= inFlight.then(() => { queued = null; return readOnce(); });
    return queued;
  }

  function onVisibility() {
    if (hidden()) cancelTimer();
    else if (running) void refresh();
  }

  return {
    refresh,
    reschedule: schedule,
    start() {
      if (running) return;
      running = true;
      doc?.addEventListener("visibilitychange", onVisibility);
      schedule();
    },
    stop() {
      running = false;
      cancelTimer();
      doc?.removeEventListener("visibilitychange", onVisibility);
      controller?.abort();
    },
    state: () => ({ failures, inFlight: inFlight !== null }),
  };
}
