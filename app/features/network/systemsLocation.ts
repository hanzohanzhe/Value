// The optional-domain results page's own state in its URL (P1 spec 0.3;
// designer ruling R-10): /runs/[runId]/systems?tab=&year=.  `tab` is the
// result domain (network_dc, network_expansion); the default (the first domain
// the Run supports) is left out, the year is written once known.  Pure
// functions only; the route view reads and writes the query.

export const SYSTEMS_TABS = ["network_dc", "network_expansion"] as const;
export type SystemsTab = (typeof SYSTEMS_TABS)[number];

export type SystemsLocation = { tab: SystemsTab | null; year: number | null };

/** The domain and year a /runs/[runId]/systems URL names; unknown values read as "not named". */
export function readSystemsLocation(search: string): SystemsLocation {
  const params = new URLSearchParams(search);
  const tab = params.get("tab");
  const year = params.get("year");
  return {
    tab: (SYSTEMS_TABS as readonly string[]).includes(tab ?? "") ? tab as SystemsTab : null,
    year: year != null && /^\d{1,4}$/.test(year) ? Number(year) : null,
  };
}

/** The domain to show: the linked one when the Run supports it, else the first supported one. */
export function systemsTab<T extends string>(available: readonly T[], wanted: string | null | undefined): T | null {
  return available.find((item) => item === wanted) ?? available[0] ?? null;
}

/** The year to show in a domain: the linked year when the domain has it, else its first year (0 when none). */
export function systemsYear(years: readonly number[] | undefined, wanted: number | null | undefined): number {
  return wanted != null && (years ?? []).includes(wanted) ? wanted : years?.[0] ?? 0;
}

/** The page's query values (null removes a key, so defaults stay out of the URL). */
export function systemsQueryValues(state: { tab: string | null; year: number }, firstTab: string | null): Record<"tab" | "year", string | number | null> {
  return {
    tab: state.tab && state.tab !== firstTab ? state.tab : null,
    year: state.year || null,
  };
}
