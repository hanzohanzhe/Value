/** Every API request goes to the page's own origin; the VALUE UI gateway
 * forwards /api/* to the local engine with the session it holds (P0-1).
 * The browser never learns an API port or a session token. */
export const API_BASE = "/api";

export function apiUrl(path: string): string {
  return `${API_BASE}/${String(path).replace(/^\/+/, "")}`;
}

/** Error codes meaning "this page did not come through the VALUE launcher"
 * (UI gateway or API refused the page's origin, host or session). */
const LAUNCHER_ERROR_CODES = new Set([
  "GF_HOST_REJECTED",
  "GF_GATEWAY_CROSS_SITE",
  "GF_GATEWAY_ORIGIN_REJECTED",
  "GF_GATEWAY_SESSION_UNAVAILABLE",
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

export async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(url, { cache: "no-store", signal });
  const payload = await response.json();
  if (isLauncherAccessFailure(response.status, payload?.error_code)) throw new LauncherAccessError(String(payload?.error_code ?? response.status));
  if (!response.ok) throw new Error(payload.error || "Request failed");
  return payload as T;
}
