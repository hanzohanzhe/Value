// S-F-高1 (R5, DECISIONS A28, four-role swap-data report): the VALUE 101 demand
// files say "mwh" in their header and MWh/period in the pack, but VALUE reads
// them as MW (half-hour average power). The backend marks such a binding with
// runtime_unit_interpretation (a registry relabel; the bytes are unchanged) and
// the role card and the mapping editor say how the file is read.

export type DemandUnitInterpretation = { declared_unit: string; runtime_unit: string; note?: string };

/** S-F-高1 (R5, A28): the unit a legacy-labelled demand file is read in, in one line; null otherwise. */
export function demandUnitText(binding: { runtime_unit_interpretation?: DemandUnitInterpretation } | undefined): string | null {
  const relabel = binding?.runtime_unit_interpretation;
  if (!relabel || relabel.runtime_unit !== "MW") return null;
  return `单位：按 MW 读取（每半小时平均功率）。文件表头写作 mwh、包内标签为 ${relabel.declared_unit}，这是已知误标；VALUE 一直按 MW 读取这些数值（每半小时电量 = MW × 0.5 h）。按这个文件的数值改写需求时，映射中请选择 MW。`;
}
