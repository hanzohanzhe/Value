// Spec 4.6 last bullet / deviation F-P08-1 (P0-8 S12): the run-time fallback
// audit as a caution notice. Pure view logic over the backend summary
// (gridform_core/zonal_results.query_runtime_fallback_audit); the backend
// decides which technology-years exceed the threshold.
import { formatNumber, withUnit } from "../shared/format.ts";
import type { ZonalRuntimeFallbackSummary } from "./networkRedispatch.ts";
import { tr } from "../../i18n/index.ts";

/** "Spatially indicative: {x}% of {tech} capacity fell back to {zone}." for every flagged technology-year. */
export function fallbackAuditSentences(audit: ZonalRuntimeFallbackSummary | null | undefined): string[] {
  const rows = Array.isArray(audit?.spatially_indicative_technologies) ? audit.spatially_indicative_technologies : [];
  const years = new Set(rows.map((row) => row.year));
  return rows.map((row) => {
    const zones = row.fallback_zone_ids?.length ? row.fallback_zone_ids.join(", ") : tr("fallback.ownZone");
    const share = withUnit(formatNumber(row.fallback_fraction * 100, 1), "%", "");
    const technology = row.technology.replaceAll("_", " ");
    return years.size > 1 ? tr("fallback.sentenceYear", { share, technology, zones, year: row.year }) : tr("fallback.sentence", { share, technology, zones });
  });
}
