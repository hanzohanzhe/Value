export type ExtensionResultItem = {
  year: number; extension_id: string; extension_version: string; namespace: string;
  manifest_sha256: string; artifact_type: string; schema_version: string; source_inputs_sha256: string;
  summary_fields: string[]; summary: Record<string, string | number | boolean | null>; unavailable_summary_fields: string[];
};
export type ExtensionResults = {
  schema_version: "value.extension-results/v1"; run_id: string;
  status: "available" | "unavailable" | "withheld" | "invalid"; reason_code: string | null; message: string | null;
  source: { year_results: { path: string; sha256: string | null }; module_resolution: { path: string; sha256: string | null } };
  identity: { container_run_id: string | null; frozen_module_graph_sha256: string | null; frozen_extension_graph_sha256: string | null };
  scope: { extension_id: string | null; year: number | null };
  capabilities: { summary_only: true; extensions: Array<{ id: string; version: string; namespace: string; manifest_sha256: string }>; years: number[]; unavailable_dimensions: string[] };
  total: number; limit: number; offset: number; count: number; has_more: boolean; items: ExtensionResultItem[];
};
export function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
const stringOrNull = (value: unknown) => value === null || typeof value === "string";
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(field => typeof field === "string");
export function isExtensionResults(value: unknown): value is ExtensionResults {
  if (!record(value) || value.schema_version !== "value.extension-results/v1" || typeof value.run_id !== "string"
    || !["available", "unavailable", "withheld", "invalid"].includes(String(value.status))
    || !stringOrNull(value.reason_code) || !stringOrNull(value.message)
    || !record(value.source) || !record(value.identity) || !record(value.scope) || !record(value.capabilities)
    || !Array.isArray(value.items) || typeof value.has_more !== "boolean") return false;
  const source = value.source, identity = value.identity, scope = value.scope, caps = value.capabilities;
  if (!["year_results", "module_resolution"].every(key => record(source[key]) && typeof source[key].path === "string" && stringOrNull(source[key].sha256))
    || !["container_run_id", "frozen_module_graph_sha256", "frozen_extension_graph_sha256"].every(key => stringOrNull(identity[key]))
    || !stringOrNull(scope.extension_id) || !(scope.year === null || Number.isSafeInteger(scope.year))
    || !["total", "limit", "offset", "count"].every(key => Number.isSafeInteger(value[key]) && Number(value[key]) >= 0)
    || caps.summary_only !== true || !strings(caps.unavailable_dimensions) || !Array.isArray(caps.years)
    || !caps.years.every(year => Number.isSafeInteger(year)) || !Array.isArray(caps.extensions)
    || !caps.extensions.every(extension => record(extension) && ["id", "version", "namespace", "manifest_sha256"].every(key => typeof extension[key] === "string"))) return false;
  return value.count === value.items.length && value.items.length <= Number(value.limit) && value.items.every(item => record(item)
    && Number.isSafeInteger(item.year) && ["extension_id", "extension_version", "namespace", "manifest_sha256", "artifact_type", "schema_version", "source_inputs_sha256"].every(key => typeof item[key] === "string")
    && strings(item.summary_fields) && strings(item.unavailable_summary_fields) && record(item.summary)
    && Object.entries(item.summary).every(([field, summary]) => (item.summary_fields as string[]).includes(field)
      && (summary === null || typeof summary === "string" || typeof summary === "boolean" || (typeof summary === "number" && Number.isFinite(summary)))));
}
