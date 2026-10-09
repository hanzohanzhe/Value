// Inspect's search in the URL (/inspect?tab=&q=, P1 spec 5.1/6.6; F3-19).
// The search box is a draft until Enter or Apply; only the applied search is
// requested and written to the URL.

export const INSPECT_SEARCH_MAX = 200;

/** The applied planning search a URL names ("" when none). */
export function readInspectSearch(search: string): string {
  return (new URLSearchParams(search).get("q") ?? "").trim().slice(0, INSPECT_SEARCH_MAX);
}

/** The text a draft applies as: trimmed and bounded. */
export function appliedSearch(draft: string): string {
  return draft.trim().slice(0, INSPECT_SEARCH_MAX);
}
