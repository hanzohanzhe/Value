import type { ParameterDefinition } from "./types";
import { Badge, labelFor } from "../shared/presentation";

function ParameterField({ definition, value, source, onChange }: { definition: ParameterDefinition; value: unknown; source: string; onChange: (value: unknown) => void }) {
  const input = definition.value_type === "boolean"
    ? <select value={String(value)} onChange={(event) => onChange(event.target.value === "true")}><option value="true">Enabled</option><option value="false">Disabled</option></select>
    : definition.value_type === "enum"
      ? <select value={String(value)} onChange={(event) => onChange(event.target.value)}>{definition.allowed_values.map((item) => <option key={String(item)} value={String(item)}>{String(item)}</option>)}</select>
      : <input type={definition.value_type === "string" ? "text" : "number"} value={String(value)} min={definition.minimum} max={definition.maximum} step={definition.value_type === "integer" ? 1 : "any"} onChange={(event) => onChange(definition.value_type === "integer" ? Number.parseInt(event.target.value, 10) : definition.value_type === "float" ? Number(event.target.value) : event.target.value)} />;
  return <label className="parameter-field"><span><b>{labelFor(definition.id)}</b><code>{definition.id}</code></span>{input}<small>{definition.scientific_effect}</small><em>{definition.unit ? `Unit: ${definition.unit}. ` : ""}Default: {String(definition.default)}{definition.minimum !== undefined ? `; range ${definition.minimum}-${definition.maximum}` : ""}</em><Badge tone={source === "Overridden" ? "blue" : "neutral"}>{source}</Badge></label>;
}

export default function AdvancedSettings({ definitions, values, resolvedSources, onChange }: { definitions: ParameterDefinition[]; values: Record<string, unknown>; resolvedSources: Record<string, { source?: string }>; onChange: (id: string, value: unknown, runtime: boolean) => void }) {
  const groups = ["Planning", "Expansion", "Storage cost", "Market experiment", "Output/runtime"];
  return <details className="advanced-settings"><summary>Advanced assumptions</summary><p>These values are read from the same parameter registry as the Python model. Change them only when the study design calls for it.</p>{groups.map((group) => <section key={group}><h4>{group}</h4><div className="parameter-grid">{definitions.filter((item) => item.group === group).map((definition) => {
    const sourceValue = resolvedSources[definition.id]?.source;
    const source = Object.hasOwn(values, definition.id) ? "Overridden" : sourceValue === "data_pack" || definition.data_pack_role ? "Data Pack-derived" : definition.category === "runtime" ? "Runtime default" : "Module default";
    return <ParameterField key={definition.id} definition={definition} value={values[definition.id] ?? definition.default} source={source} onChange={(value) => onChange(definition.id, value, definition.category === "runtime")} />;
  })}</div></section>)}</details>;
}

