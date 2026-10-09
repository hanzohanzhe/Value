// The VRE page's own state in its URL (P1 spec 0.3; designer ruling R-10):
// /runs/[runId]/vre?year=&resolution=.  A reload, a copied link or Back opens
// the same model year and timeline resolution.  The page has no period window
// (its timeline is the year at the chosen resolution), so the ruling's
// from=/window= have nothing to name here (deviation D-P1P-1).  The default
// resolution (daily) is left out; the year is written once known.  Pure
// functions only; the route view reads and writes the query.

export const VRE_RESOLUTIONS = ["daily", "weekly", "half_hour"] as const;
export type VreResolution = (typeof VRE_RESOLUTIONS)[number];

export type VreLocation = { year: number | null; resolution: VreResolution };

export const DEFAULT_VRE_LOCATION: VreLocation = { year: null, resolution: "daily" };

/** The year and resolution a /runs/[runId]/vre URL names; unknown values fall back to the defaults. */
export function readVreLocation(search: string): VreLocation {
  const params = new URLSearchParams(search);
  const year = params.get("year");
  const resolution = params.get("resolution");
  return {
    year: year != null && /^\d{1,4}$/.test(year) ? Number(year) : null,
    resolution: (VRE_RESOLUTIONS as readonly string[]).includes(resolution ?? "") ? resolution as VreResolution : DEFAULT_VRE_LOCATION.resolution,
  };
}

/** The year to show: the linked year when the Run published it, else the first published year (0 when none). */
export function vreYear(years: readonly number[], wanted: number | null | undefined): number {
  return wanted != null && years.includes(wanted) ? wanted : years[0] ?? 0;
}

/** The page's query values (null removes a key, so defaults stay out of the URL). */
export function vreQueryValues(state: { year: number; resolution: string }): Record<"year" | "resolution", string | number | null> {
  return {
    year: state.year || null,
    resolution: state.resolution === DEFAULT_VRE_LOCATION.resolution ? null : state.resolution,
  };
}
