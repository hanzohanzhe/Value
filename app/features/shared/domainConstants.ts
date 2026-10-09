import { localizedTable, type MessageKey } from "../../i18n/index.ts";

export const PUBLIC_CAPABILITY_DOMAINS = ["network_dc", "hydrology", "network_expansion"];

/** Public names of the optional result domains (P0-9 S10). AC feasibility is
 * not a public domain of this release and has no label here. */
export const DOMAIN_LABELS: Readonly<Record<string, string>> = localizedTable<string>({
  network_dc: "domain.network_dc",
  hydrology: "domain.hydrology",
  network_expansion: "domain.network_expansion",
  zonal_redispatch: "domain.zonal_redispatch",
} as Record<string, MessageKey>);

export function domainLabel(id: string): string {
  return DOMAIN_LABELS[id] ?? id.replaceAll("_", " ");
}
