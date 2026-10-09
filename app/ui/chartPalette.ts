// Technology colours and patterns for charts (spec 1.2). Colours are the
// --tech-* tokens; where two series share a colour, or the colour alone would
// not be enough, a pattern tells them apart.

export type SeriesPattern = "solid" | "hatch" | "dots";
export type SeriesStyle = { color: string; pattern: SeriesPattern };

export const TECH_SERIES = {
  wind_onshore: { color: "var(--tech-wind)", pattern: "solid" },
  wind_offshore: { color: "var(--tech-wind)", pattern: "hatch" },
  solar: { color: "var(--tech-solar)", pattern: "solid" },
  unused_vre: { color: "var(--tech-unused-vre)", pattern: "hatch" },
  nuclear: { color: "var(--tech-nuclear)", pattern: "solid" },
  ccgt: { color: "var(--tech-gas)", pattern: "solid" },
  ocgt: { color: "var(--tech-gas)", pattern: "hatch" },
  biomass: { color: "var(--tech-biomass)", pattern: "solid" },
  hydro: { color: "var(--tech-hydro)", pattern: "solid" },
  pumped_hydro: { color: "var(--tech-hydro)", pattern: "hatch" },
  storage: { color: "var(--tech-storage)", pattern: "solid" },
  import: { color: "var(--tech-import)", pattern: "dots" },
  shortfall: { color: "var(--tech-shortfall)", pattern: "solid" },
} as const satisfies Record<string, SeriesStyle>;

export type TechSeriesKey = keyof typeof TECH_SERIES;

// Model technology ids (data packs, run results) to chart series.
const TECH_ALIASES: Record<string, TechSeriesKey> = {
  onshore_wind: "wind_onshore",
  offshore_wind: "wind_offshore",
  wind: "wind_onshore",
  solar_pv: "solar",
  unused_vre: "unused_vre",
  curtailment: "unused_vre",
  natural_flow_hydro: "hydro",
  reservoir_hydro: "hydro",
  battery_storage: "storage",
  hydrogen_storage: "storage",
  boundary_import: "import",
  interconnector_import: "import",
  biomass_and_waste: "biomass",
  shortfall_mwh: "shortfall",
  unserved_energy: "shortfall",
};

/** The series style of a technology id, or null when it has no chart colour. */
export function techSeries(technology: string): SeriesStyle | null {
  const key = (Object.hasOwn(TECH_SERIES, technology) ? technology : TECH_ALIASES[technology]) as TechSeriesKey | undefined;
  return key ? TECH_SERIES[key] : null;
}
