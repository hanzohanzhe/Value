// The single API client of the VALUE frontend (P1 spec 4).
//
// Every request goes to the page's own origin: the VALUE UI gateway forwards
// /api/* to the local engine with the session it holds (P0-1).  The browser
// never learns an API port, an origin or a session token, so no API origin is
// defined anywhere in the frontend: API_BASE below is a same-origin path.
//
// Rules kept here for every caller:
//   * the HTTP status is checked before the body is read as data;
//   * every request has a timeout (AbortController): 30 s for ordinary reads,
//     longer for the long tasks listed in LONG_READ_PATHS and for mutations;
//   * a refused request is an ApiError { status, code, message, detail };
//     a page that did not come through the launcher is a LauncherAccessError.
//
// The only other network calls are the XMLHttpRequest uploads with progress
// (data packs, research suite), which fetch() cannot report.

import { tr } from "../i18n/index.ts";

export const API_BASE = "/api";

export function apiUrl(path: string): string {
  return `${API_BASE}/${String(path).replace(/^\/+/, "")}`;
}

/** Ordinary request timeout (spec 4). */
export const DEFAULT_TIMEOUT_MS = 30_000;
/** Long tasks: run-result reads over a whole ledger and every mutation. */
export const LONG_TIMEOUT_MS = 10 * 60_000;

/** Reads that can legitimately take longer than 30 s on a large Run (whole-year ledgers, comparisons, exports). */
const LONG_READ_PATHS = [
  /\/api\/runs\/[^/?]+\/(?:market|domains|results|network|zonal|extensions|replay-exports|artifacts)\b/,
  /\/api\/comparisons\b/,
  /\/api\/data-workbench\//,
];

/** The timeout a request gets when the caller does not choose one. */
export function defaultTimeoutMs(url: string, method = "GET"): number {
  const verb = method.toUpperCase();
  if (verb !== "GET" && verb !== "HEAD") return LONG_TIMEOUT_MS;
  return LONG_READ_PATHS.some((pattern) => pattern.test(url)) ? LONG_TIMEOUT_MS : DEFAULT_TIMEOUT_MS;
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

/** A refused or failed API request (P0-3 S8, spec 4). `status` is 0 when no answer arrived (timeout). */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  /** The parsed error body, when the service sent one. */
  readonly detail: unknown;
  constructor(message: string, status: number, code: string | null, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export const TIMEOUT_ERROR_CODE = "GF_REQUEST_TIMEOUT";

export type ApiRequestInit = RequestInit & {
  /** Milliseconds before the request is abandoned; defaults to defaultTimeoutMs(url, method). */
  timeoutMs?: number;
};

function linkSignals(outer: AbortSignal | null | undefined, controller: AbortController): () => void {
  if (!outer) return () => undefined;
  if (outer.aborted) { controller.abort(outer.reason); return () => undefined; }
  const forward = () => controller.abort(outer.reason);
  outer.addEventListener("abort", forward, { once: true });
  return () => outer.removeEventListener("abort", forward);
}

/**
 * fetch() with the client's timeout.  The caller's own AbortSignal still
 * cancels the request (and rejects with its AbortError, as fetch does); the
 * timeout rejects with ApiError(status 0, GF_REQUEST_TIMEOUT).
 * The Response is returned as is: callers that read error bodies themselves
 * (409 confirmations, pending-Run refusals) keep doing so.
 */
export async function apiFetch(url: string, init: ApiRequestInit = {}): Promise<Response> {
  const { timeoutMs, signal, ...rest } = init;
  const limit = timeoutMs ?? defaultTimeoutMs(url, rest.method);
  const controller = new AbortController();
  const unlink = linkSignals(signal, controller);
  let timedOut = false;
  const timer = limit > 0 ? setTimeout(() => { timedOut = true; controller.abort(); }, limit) : null;
  try {
    return await globalThis.fetch(url, { ...rest, signal: controller.signal });
  } catch (error) {
    if (timedOut) throw new ApiError(tr("api.timeout", { seconds: Math.round(limit / 1000) }), 0, TIMEOUT_ERROR_CODE);
    throw error;
  } finally {
    if (timer !== null) clearTimeout(timer);
    unlink();
  }
}

type ErrorBody = { error?: unknown; error_code?: unknown };

function errorMessage(body: ErrorBody | null, status: number): string {
  if (body && typeof body.error === "string" && body.error) return body.error;
  return tr("api.requestFailed", { status });
}

/**
 * Read a Response as JSON data: the status first (an error status is an
 * ApiError or LauncherAccessError, whatever its body), then the body (an
 * unreadable body is ApiError GF_RESPONSE_UNREADABLE, never data).
 */
export async function readJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let body: ErrorBody | null = null;
    try { body = await response.json() as ErrorBody; } catch { /* a non-JSON error body: the status decides */ }
    const code = body && typeof body.error_code === "string" ? body.error_code : null;
    if (isLauncherAccessFailure(response.status, code)) throw new LauncherAccessError(String(code ?? response.status));
    throw new ApiError(errorMessage(body, response.status), response.status, code, body);
  }
  let payload: unknown = null;
  try { payload = await response.json(); } catch { /* unreadable: reported below */ }
  if (payload === null) throw new ApiError(tr("api.unreadable"), response.status, "GF_RESPONSE_UNREADABLE");
  return payload as T;
}

/** GET a JSON resource (no caching). */
export async function getJson<T>(url: string, signal?: AbortSignal, options: { timeoutMs?: number } = {}): Promise<T> {
  return readJson<T>(await apiFetch(url, { cache: "no-store", signal, timeoutMs: options.timeoutMs }));
}

/** Send a JSON body (POST by default) and read the JSON answer. */
export async function sendJson<T>(url: string, body: unknown, init: Omit<ApiRequestInit, "body"> = {}): Promise<T> {
  const headers = { "Content-Type": "application/json", ...(init.headers as Record<string, string> | undefined ?? {}) };
  return readJson<T>(await apiFetch(url, { method: "POST", ...init, headers, body: JSON.stringify(body ?? {}) }));
}

export type RefreshFailure = "launcher" | "service_error" | "unreachable";

/** How a failed workspace refresh should be shown: a launcher problem is the
 * whole-page notice; an answer with an error status is a degraded service;
 * no answer at all (network error, timeout) counts towards "offline". */
export function classifyRefreshFailure(error: unknown): RefreshFailure {
  if (error instanceof LauncherAccessError) return "launcher";
  if (error instanceof ApiError && error.status > 0) return "service_error";
  return "unreachable";
}

// ------------------------------------------------------------ contract version

/**
 * The frontend/backend contract this interface was built for (spec 4).  The
 * local service reports its own value as `frontend_contract_version` in
 * /api/health and /api/workspace (gridform_core/frontend_contract.py);
 * tests/test_local_api_boundary.py keeps the two equal.  Raise it
 * on both sides together whenever an API change would break the other half.
 */
export const FRONTEND_CONTRACT_VERSION = "value.expanded-frontend/v1";

export type ContractStatus = "unknown" | "match" | "mismatch";

/** "unknown" until /api/health answered; a service that does not report a contract predates it. */
export function contractStatus(health: { frontend_contract_version?: unknown } | null | undefined): ContractStatus {
  if (!health) return "unknown";
  return health.frontend_contract_version === FRONTEND_CONTRACT_VERSION ? "match" : "mismatch";
}
