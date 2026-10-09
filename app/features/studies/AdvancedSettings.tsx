"use client";

// Advanced assumptions of a Study (the parameter registry).  F4-02 / P1 spec
// 6.2: integer and float parameters use NumberField, so clearing a box never
// becomes 0 (or NaN); an empty or out-of-range value is flagged at once, is not
// applied, and blocks saving (the composer refuses to save while a box is invalid).
import type { ParameterDefinition } from "./types";
import { Badge, labelFor } from "../shared/presentation";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/index.ts";
import { NumberField } from "../../ui";

type Source = "overridden" | "dataPack" | "runtime" | "module";
const SOURCE_KEYS: Record<Source, MessageKey> = {
  overridden: "studies.assumptions.sourceOverridden", dataPack: "studies.assumptions.sourceDataPack",
  runtime: "studies.assumptions.sourceRuntime", module: "studies.assumptions.sourceModule",
};
const GROUPS: { id: string; key: MessageKey }[] = [
  { id: "Planning", key: "studies.assumptions.groupPlanning" }, { id: "Expansion", key: "studies.assumptions.groupExpansion" },
  { id: "Storage cost", key: "studies.assumptions.groupStorageCost" }, { id: "Market experiment", key: "studies.assumptions.groupMarket" },
  { id: "Output/runtime", key: "studies.assumptions.groupRuntime" },
];

function ParameterField({ definition, value, source, onChange }: { definition: ParameterDefinition; value: unknown; source: Source; onChange: (value: unknown) => void }) {
  const t = useT();
  const note = <><small>{definition.scientific_effect}</small><em>{[
    definition.unit ? t("studies.assumptions.unit", { unit: definition.unit }) : "",
    t("studies.assumptions.default", { value: String(definition.default) }),
    definition.minimum !== undefined ? t("studies.assumptions.range", { min: definition.minimum, max: definition.maximum ?? "" }) : "",
  ].filter(Boolean).join(" · ")}</em><Badge tone={source === "overridden" ? "blue" : "neutral"}>{t(SOURCE_KEYS[source])}</Badge></>;
  if (definition.value_type === "integer" || definition.value_type === "float") {
    return <div className="parameter-field">
      <NumberField label={<><b>{labelFor(definition.id)}</b> <code>{definition.id}</code></>} value={typeof value === "number" && Number.isFinite(value) ? value : null}
        min={definition.minimum} max={definition.maximum} step={definition.value_type === "integer" ? 1 : undefined} unit={definition.unit} required
        onChange={(next, check) => { if (check.valid && next !== null) onChange(next); }} />
      {note}
    </div>;
  }
  const input = definition.value_type === "boolean"
    ? <select value={String(value)} onChange={(event) => onChange(event.target.value === "true")}><option value="true">{t("studies.assumptions.enabled")}</option><option value="false">{t("studies.assumptions.disabled")}</option></select>
    : definition.value_type === "enum"
      ? <select value={String(value)} onChange={(event) => onChange(event.target.value)}>{definition.allowed_values.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select>
      : <input type="text" value={String(value)} onChange={(event) => onChange(event.target.value)} />;
  return <label className="parameter-field"><span><b>{labelFor(definition.id)}</b><code>{definition.id}</code></span>{input}{note}</label>;
}

export default function AdvancedSettings({ definitions, values, resolvedSources, onChange }: { definitions: ParameterDefinition[]; values: Record<string, unknown>; resolvedSources: Record<string, { source?: string }>; onChange: (id: string, value: unknown, runtime: boolean) => void }) {
  const t = useT();
  return <details className="advanced-settings"><summary>{t("studies.assumptions.summary")}</summary><p>{t("studies.assumptions.lead")}</p>{GROUPS.map((group) => <section key={group.id}><h4>{t(group.key)}</h4><div className="parameter-grid">{definitions.filter((item) => item.group === group.id).map((definition) => {
    const sourceValue = resolvedSources[definition.id]?.source;
    const source: Source = Object.hasOwn(values, definition.id) ? "overridden" : sourceValue === "data_pack" || definition.data_pack_role ? "dataPack" : definition.category === "runtime" ? "runtime" : "module";
    return <ParameterField key={definition.id} definition={definition} value={values[definition.id] ?? definition.default} source={source} onChange={(value) => onChange(definition.id, value, definition.category === "runtime")} />;
  })}</div></section>)}</details>;
}
