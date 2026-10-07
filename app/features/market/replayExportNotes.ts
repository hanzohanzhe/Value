// What the period columns of a replay export mean where they differ from the
// annual ledgers (R4, four-role report R-低9).
//
// period_summary.physical_resource_cost_gbp is the PSM kernel's retained
// period cost: accepted offers at their offer prices (generation offers,
// storage offers, curtailment payments). The cost ledger's annual operating
// resource cost (value.native-operating-cost/v1) instead counts generation at
// dispatch unit cost, imports, start-up adders, unserved energy at VoLL and
// storage cycle wear. VALUE 101 corrected 2025: £7,304,311.46 summed over the
// periods against £7,304,116.11 in the ledger; the £195.35 are the storage
// offer mark-up over cycle wear (£185.19), curtailment payments (£10.39) and
// rounding of generation offers to unit cost (-£0.23).

export const PERIOD_COST_COLUMN_NOTE = "physical_resource_cost_gbp in period rows is the market kernel's retained period cost: accepted offers at their offer prices, including storage offers and curtailment payments. The annual operating resource cost in the cost ledger counts storage at its cycle wear and excludes curtailment payments, so the sum over a year differs slightly (VALUE 101, 2025: about £195, 0.003%). Use the cost ledger for annual totals.";

/** The note under the export controls; the ZIP carries the ledgers as well, so every format shows it. */
export function replayExportNote(format: string): string | null {
  return ["csv", "jsonl", "zip"].includes(format) ? PERIOD_COST_COLUMN_NOTE : null;
}
