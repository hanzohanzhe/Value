// The network page's own state in its URL (P1 spec 0.3 and 5.1; W6):
// /runs/[runId]/network?year=&tab=&from=&window=.  A reload, a copied link or
// Back opens the same model year, tab and period window.  Defaults (the first
// year the Run published, the Overview tab, period 0, 24 hours) are left out of
// the URL.  Pure functions only; the route view reads and writes the query.

export const NETWORK_TABS = ["overview", "period", "reliability", "evidence"] as const;
export type NetworkTab = (typeof NETWORK_TABS)[number];
/** Period windows of the network page: 48 half-hours (24 hours) or 336 (168 hours). */
export const NETWORK_WINDOWS = [48, 336] as const;
export type NetworkWindow = (typeof NETWORK_WINDOWS)[number];

export type NetworkLocation = { year: number | null; tab: NetworkTab; from: number; window: NetworkWindow };

export const DEFAULT_NETWORK_LOCATION: NetworkLocation = { year: null, tab: "overview", from: 0, window: 48 };

/** The year, tab, first period and window a /runs/[runId]/network URL names; unknown values fall back to the defaults. */
export function readNetworkLocation(search: string): NetworkLocation {
  const params = new URLSearchParams(search);
  const integer = (name: string, digits: number) => {
    const value = params.get(name);
    return value != null && new RegExp(`^\\d{1,${digits}}$`).test(value) ? Number(value) : null;
  };
  const tab = params.get("tab");
  const window = integer("window", 3);
  return {
    year: integer("year", 4),
    tab: (NETWORK_TABS as readonly string[]).includes(tab ?? "") ? tab as NetworkTab : DEFAULT_NETWORK_LOCATION.tab,
    from: integer("from", 6) ?? DEFAULT_NETWORK_LOCATION.from,
    window: (NETWORK_WINDOWS as readonly number[]).includes(window ?? -1) ? window as NetworkWindow : DEFAULT_NETWORK_LOCATION.window,
  };
}

/** The year to show: the linked or current year when the Run has it, else the fallback (the first published year). */
export function networkYear(years: readonly number[], wanted: number | null | undefined, fallback: number | null): number | null {
  return wanted != null && years.includes(wanted) ? wanted : fallback;
}

/** The page's query values for a state (null removes a key, so defaults stay out of the URL). */
export function networkQueryValues(state: { year: number | null; tab: NetworkTab; from: number; window: NetworkWindow }): Record<"year" | "tab" | "from" | "window", string | number | null> {
  return {
    year: state.year,
    tab: state.tab === DEFAULT_NETWORK_LOCATION.tab ? null : state.tab,
    from: state.from > 0 ? state.from : null,
    window: state.window === DEFAULT_NETWORK_LOCATION.window ? null : state.window,
  };
}
