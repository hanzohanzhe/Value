/** Every API request goes to the page's own origin; the VALUE UI gateway
 * forwards /api/* to the local engine with the session it holds (P0-1).
 * The browser never learns an API port or a session token. */
export const API_BASE = "/api";

export function apiUrl(path: string): string {
  return `${API_BASE}/${String(path).replace(/^\/+/, "")}`;
}

/** Error codes meaning "this page did not come through the VALUE launcher"
 * (UI gateway or API refused the page's origin, host or session).  A missing
 * session file (GF_GATEWAY_SESSION_UNAVAILABLE) is not among them: it usually
 * means the engine is still starting or stopped, which the rail shows as
 * "Model service offline" with Retry. */
const LAUNCHER_ERROR_CODES = new Set([
  "GF_HOST_REJECTED",
  "GF_GATEWAY_CROSS_SITE",
  "GF_GATEWAY_ORIGIN_REJECTED",
  "GF_GATEWAY_SESSION_MISMATCH",
  "GF_BROWSER_ORIGIN_REJECTED",
  "GF_SESSION_REQUIRED",
  "GF_SESSION_INVALID",
]);

export class LauncherAccessError extends Error {
  readonly code: string;
  constructor(code: string) {
    super("Open VALUE from its launcher");
    this.name = "LauncherAccessError";
    this.code = code;
  }
}

/** True when a response says the page cannot talk to the local engine at all. */
export function isLauncherAccessFailure(status: number, code: unknown): boolean {
  if (status === 421) return true;
  return (status === 403 || status === 502) && typeof code === "string" && LAUNCHER_ERROR_CODES.has(code);
}

/** A refused or failed API request with its HTTP status and VALUE error code (P0-3 S8). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  constructor(message: string, status: number, code: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { cache: "no-store", signal });
  let payload: { error?: string; error_code?: string } | null = null;
  try { payload = await response.json(); } catch { /* a non-JSON body: the status decides */ }
  if (isLauncherAccessFailure(response.status, payload?.error_code)) throw new LauncherAccessError(String(payload?.error_code ?? response.status));
  if (!response.ok) throw new ApiError(payload?.error || `Request failed (HTTP ${response.status})`, response.status, payload?.error_code ?? null);
  if (payload === null) throw new ApiError("The service returned an unreadable response", response.status, "GF_RESPONSE_UNREADABLE");
  return payload as T;
}

export type RefreshFailure = "launcher" | "service_error" | "unreachable";

/** How a failed workspace refresh should be shown: a launcher problem is the
 * whole-page notice; an answer with an error status is a degraded service;
 * no answer at all (network error) counts towards "offline". */
export function classifyRefreshFailure(error: unknown): RefreshFailure {
  if (error instanceof LauncherAccessError) return "launcher";
  if (error instanceof ApiError && error.status > 0) return "service_error";
  return "unreachable";
}

export type ServiceState = "loading" | "online" | "degraded" | "offline";

/** Consecutive failures before the rail says "Backend offline" (spec 5). */
export const OFFLINE_AFTER_FAILURES = 3;
export const POLL_BASE_MS = 2_000;
export const POLL_MAX_MS = 30_000;

/** Polling interval after `failures` consecutive failures: 2 s doubling to at most 30 s. */
export function pollDelay(failures: number): number {
  return Math.min(POLL_MAX_MS, POLL_BASE_MS * 2 ** Math.max(0, failures));
}

/** Service state from the last health status and the consecutive refresh failures. */
export function serviceState(failures: number, healthStatus: string | null | undefined, loaded: boolean): ServiceState {
  if (failures >= OFFLINE_AFTER_FAILURES) return "offline";
  if (failures > 0 || healthStatus === "degraded") return "degraded";
  return loaded ? "online" : "loading";
}
