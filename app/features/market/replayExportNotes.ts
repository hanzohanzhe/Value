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

import { en } from "../../i18n/en.ts";
import { tr } from "../../i18n/index.ts";

/** English text of the message "exportNote.periodCost" (the panel shows it in the interface language). */
export const PERIOD_COST_COLUMN_NOTE = en["exportNote.periodCost"];

/** The note under the export controls; the ZIP carries the ledgers as well, so every format shows it. */
export function replayExportNote(format: string): string | null {
  return ["csv", "jsonl", "zip"].includes(format) ? tr("exportNote.periodCost") : null;
}
