export const PUBLIC_CAPABILITY_DOMAINS = ["network_dc", "hydrology", "network_expansion"];

/** Public names of the optional result domains (P0-9 S10). AC feasibility is
 * not a public domain of this release and has no label here. */
export const DOMAIN_LABELS: Record<string, string> = {
  network_dc: "DC network",
  hydrology: "Natural-flow hydrology",
  network_expansion: "Transmission expansion",
  zonal_redispatch: "Zonal network & redispatch",
};

export function domainLabel(id: string): string {
  return DOMAIN_LABELS[id] ?? id.replaceAll("_", " ");
}
