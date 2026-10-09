// S-F-高1 (R5, DECISIONS A28, four-role swap-data report): the VALUE 101 demand
// files say "mwh" in their header and MWh/period in the pack, but VALUE reads
// them as MW (half-hour average power). The backend marks such a binding with
// runtime_unit_interpretation (a registry relabel; the bytes are unchanged) and
// the role card and the mapping editor say how the file is read.
// P1 W4b: the sentence is the dictionary entry journeyData.demandUnit (English
// by default; the R5 Chinese wording is its zh entry).
import { translator, type Translate } from "../../i18n/index.ts";

const ENGLISH = translator("en");

export type DemandUnitInterpretation = { declared_unit: string; runtime_unit: string; note?: string };

/** S-F-高1 (R5, A28): the unit a legacy-labelled demand file is read in, in one line; null otherwise. */
export function demandUnitText(binding: { runtime_unit_interpretation?: DemandUnitInterpretation } | undefined, t: Translate = ENGLISH): string | null {
  const relabel = binding?.runtime_unit_interpretation;
  if (!relabel || relabel.runtime_unit !== "MW") return null;
  return t("journeyData.demandUnit", { declared: relabel.declared_unit });
}
