// Annual cost composition of the Runs page (P0-9 S9; spec 4.3; F3-04).
// The composition is chosen by the recorded cost definition; the stacked bar
// always adds up to the headline total (a reconciliation residual makes up any
// recorded difference) and a mechanism the method does not model is listed as
// "Not modelled", never drawn as £0.
import { formatMoney as formatMoneyText, formatNumber, withUnit } from "../shared/format.ts";

export type MetricMap = Record<string, number | string | boolean | null | undefined>;

export type CostSegment = { key: string; label: string; amount: number; share: number; colour: string; className?: string };
export type CostRow = { key: string; label: string; amount: number | null; state?: "not_modelled" | "not_recorded"; note?: string };

export type CostComposition = {
  definition: "native" | "legacy" | "unknown";
  headline: number | null;
  /** Bar segments; their amounts add up to the headline exactly. */
  segments: CostSegment[];
  /** Every row of the composition table, including not-modelled and memo rows. */
  rows: CostRow[];
  vollNote: "includes VoLL" | "excludes VoLL" | "VoLL basis not recorded";
  /** C30: the recorded VoLL part of the operating cost, for the note's tooltip. */
  vollTitle?: string;
  reconciled: boolean;
};

// Colours already used by the existing charts (globals.css .cost-stack and the
// technology palette); no new palette.
const COLOURS = {
  capital: "var(--blue)", operating: "var(--teal)", lost_value: "#d26d4f",
  capacity_mechanism: "#7a64c5", decarbonisation: "#df8a34", residual: "#b3bac6",
};
const NATIVE_DEFINITION = "value.cem-system-resource-cost/v1";
const LEGACY_DEFINITION = "legacy_storage_tariff";
const TOLERANCE_GBP = 0.5;

function number(metrics: MetricMap, key: string): number | null {
  const value = metrics[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function costComposition(metrics: MetricMap): CostComposition {
  const definitionId = String(metrics.system_cost_definition_id ?? "");
  const definition = definitionId === NATIVE_DEFINITION ? "native" : definitionId === LEGACY_DEFINITION ? "legacy" : "unknown";
  const headline = number(metrics, "total_system_cost_gbp");
  const capital = number(metrics, "total_levelized_capital_cost_gbp");
  const operating = number(metrics, "total_operational_cost_gbp");
  const includesVoll = metrics.system_cost_includes_voll;
  const vollNote = includesVoll === true ? "includes VoLL" : includesVoll === false ? "excludes VoLL" : definition === "legacy" ? "includes VoLL" : "VoLL basis not recorded";

  const mechanism = (key: string, statusKey: string, label: string): CostRow => {
    const amount = number(metrics, key);
    const status = String(metrics[statusKey] ?? "");
    if (status === "not_modelled" || (definition === "native" && amount == null)) return { key, label, amount: null, state: "not_modelled" };
    return amount == null ? { key, label, amount: null, state: "not_recorded" } : { key, label, amount };
  };
  const capitalRow: CostRow = { key: "capital", label: "Annualised capital", amount: capital, state: capital == null ? "not_recorded" : undefined };
  const operatingRow: CostRow = { key: "operating", label: "Operating cost", amount: operating, state: operating == null ? "not_recorded" : undefined };
  const capacityRow = mechanism("cm_mechanism_cost_gbp", "cm_mechanism_cost_status", "Capacity mechanism");
  const decarbonisationRow = mechanism("decarbonization_mechanism_cost_gbp", "decarbonization_mechanism_cost_status", "Decarbonisation policy");

  // Components that are part of the headline under this definition.
  const included: { row: CostRow; colour: string; className?: string }[] = [
    { row: capitalRow, colour: COLOURS.capital, className: "capital" },
    { row: operatingRow, colour: COLOURS.operating, className: "operating" },
  ];
  const rows: CostRow[] = [capitalRow, operatingRow];
  if (definition === "legacy") {
    const lostValue = number(metrics, "lost_value_of_electricity_gbp");
    const lostRow: CostRow = { key: "lost_value", label: "Value of lost load (VoLL)", amount: lostValue, state: lostValue == null ? "not_recorded" : undefined };
    included.push({ row: lostRow, colour: COLOURS.lost_value });
    if (capacityRow.amount != null) included.push({ row: capacityRow, colour: COLOURS.capacity_mechanism, className: "capacity-market" });
    if (decarbonisationRow.amount != null) included.push({ row: decarbonisationRow, colour: COLOURS.decarbonisation, className: "policy" });
    rows.push(lostRow, capacityRow, decarbonisationRow);
  } else {
    // Native: the mechanisms are not part of the CEM resource cost; list them only.
    rows.push(capacityRow, decarbonisationRow);
  }

  const known = included.filter((item) => item.row.amount != null);
  const knownSum = known.reduce((sum, item) => sum + (item.row.amount ?? 0), 0);
  const residual = headline == null ? null : headline - knownSum;
  const reconciled = headline != null && residual != null && residual >= -TOLERANCE_GBP;
  const segments: CostSegment[] = [];
  if (headline != null && headline > 0 && reconciled) {
    for (const item of known) segments.push({ key: item.row.key, label: item.row.label, amount: item.row.amount!, share: item.row.amount! / headline, colour: item.colour, className: item.className });
    if (residual! > TOLERANCE_GBP) segments.push({ key: "residual", label: "Reconciliation residual", amount: residual!, share: residual! / headline, colour: COLOURS.residual });
  }
  if (residual != null && Math.abs(residual) > TOLERANCE_GBP) rows.push({ key: "residual", label: "Reconciliation residual", amount: residual, note: "Recorded headline minus its recorded components" });

  const memo = number(metrics, "ror_hydro_compatibility_capital_gbp");
  if (memo != null) rows.push({ key: "memo_ror_hydro", label: "Memo: run-of-river hydro compatibility capital (excluded from headline)", amount: memo, note: "excluded" });

  // C30 (P0-6 S4): the native operating cost books recorded blackout x VoLL; say how much.
  const vollCost = number(metrics, "operating_cost_voll_gbp");
  const voll = number(metrics, "voll_gbp_per_mwh");
  const vollTitle = vollCost != null
    ? `Operating cost includes ${formatMoneyText(vollCost)} of recorded unserved energy${voll != null ? ` valued at ${withUnit(formatNumber(voll), "/MWh", "", "£")}` : ""}.`
    : undefined;
  return { definition, headline, segments, rows, vollNote, vollTitle, reconciled };
}

/** Sum of the bar segments (equals the headline for a reconciled composition). */
export function segmentTotal(composition: Pick<CostComposition, "segments">): number {
  return composition.segments.reduce((sum, segment) => sum + segment.amount, 0);
}

/**
 * Designer ruling 1 (M2 UI review): the denominator of the average-cost figure
 * follows the recorded cost definition. The CEM ledger divides by demand
 * served; the legacy total (total_system_cost / total_energy_generated) by
 * energy generated; an unknown definition says so instead of guessing.
 */
export function unitCostText(metrics: MetricMap): string {
  const value = number(metrics, "cost_per_mwh_gbp");
  if (value == null) return "Not evaluated";
  const price = withUnit(formatNumber(value), "/MWh", "", "£");
  const definitionId = String(metrics.system_cost_definition_id ?? "");
  if (definitionId === NATIVE_DEFINITION) return `${price} served`;
  if (definitionId === LEGACY_DEFINITION) return `${price} generated`;
  return `${price} (basis not recorded)`;
}

/**
 * S-F-中2 (R5): the annual card's unserved demand is all unserved energy of
 * the A2 account (the PSM-recorded blackout plus the stress shortfall that the
 * energy-balance ledger books as unserved), the same quantity the cost per MWh
 * served deducts; the PSM-recorded part is named beside it. Both values come
 * from the backend; the page does not subtract. A Run without the A2 value
 * shows the recorded blackout with no note.
 */
/**
 * R5 R-中2: unused VRE at the PSM boundary (available minus accepted VRE, the
 * VRE page's figure) with its share of available VRE. Every PSM records it;
 * the v2 curtailment attribution needs matched counterfactual snapshots.
 */
export function unusedVreText(metrics: MetricMap): string {
  const unused = number(metrics, "unused_vre_mwh");
  if (unused == null) return "Not recorded";
  const available = number(metrics, "available_vre_mwh");
  const share = available != null && available > 0 ? ` · ${withUnit(formatNumber(100 * unused / available, 1), "%", "")} of available` : "";
  return `${withUnit(formatNumber(unused), "MWh")}${share}`;
}

export function unservedDemandText(metrics: MetricMap): { value: string; note: string | null } {
  const energy = (value: number | null) => value == null ? "Not evaluated" : withUnit(formatNumber(value), "MWh");
  const total = number(metrics, "unserved_energy_a2_mwh");
  const recorded = number(metrics, "blackout_mwh");
  if (total == null) return { value: energy(recorded), note: null };
  return { value: energy(total), note: `incl. stress shortfall · ${energy(recorded)} recorded by the PSM` };
}
