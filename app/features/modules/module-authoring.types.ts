export type AuthorModule = { id: string; name: string; slot: string; version: string; status: string };
export type AuthorStudy = {
  id: string; name: string; data_pack_id: string; revision_sha256?: string;
  start_year: number; end_year: number; modules: Record<string, string>;
  purpose?: string; parameters?: Record<string, unknown>; runtime_options?: Record<string, unknown>;
  selected_extensions?: string[]; extension_parameters?: Record<string, unknown>;
  maturity_acknowledgements?: Record<string, string>; market_configuration?: unknown; solver_contract?: unknown;
};
export type AuthoringDetail = {
  schema_version: "value.module-authoring/v1"; module_id: string; identity_sha256: string;
  identity: { module_id: string; module_version: string; slot: string; contract_version: string;
    entry_point: string; source_sha256: string | null; scientific_version: string | null; execution_kind: string };
  manifest: Record<string, unknown> & {
    id: string; version: string; slot: string; contract_version: string; status: string;
    inputs: string[]; outputs: string[]; state_reads: string[]; state_writes: string[];
    parameters: string[]; provides_capabilities: string[]; requires_capabilities: string[];
    artifacts: string[]; units: Record<string, string>; determinism: string;
  };
  methods: string[];
  source: { available: boolean; filename: string | null; content: string | null; truncated: boolean; reason: string | null };
  conformance: { status: "passed" | "failed" | "not_run"; errors: string[]; warnings: string[];
    scientific_validation_status: string; origin: string | null };
};
export type AuthorDraftResolution = {
  schema_version: "value.study-draft-resolution/v1"; valid: boolean;
  errors: Array<{ code: string; message: string; scope: string }>;
  warnings: Array<{ code: string; message: string; scope: string }>;
  compatible_modules: Record<string, Array<{ id: string; compatible: boolean; reason?: string | null }>>;
  graph_preview?: { modules?: Record<string, { module_id: string; module_version: string; contract_version: string }> } | null;
  maturity: { acknowledgements_required: Array<{ key: string; id: string; version: string; maturity: string; acknowledgement: string }> };
};
export function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === "string");
export function isAuthoringDetail(value: unknown): value is AuthoringDetail {
  if (!record(value) || value.schema_version !== "value.module-authoring/v1" || typeof value.module_id !== "string"
    || typeof value.identity_sha256 !== "string" || !record(value.identity) || !record(value.manifest)
    || !record(value.source) || !record(value.conformance) || !strings(value.methods)) return false;
  const identity = value.identity, manifest = value.manifest, source = value.source, conformance = value.conformance;
  return ["module_id", "module_version", "slot", "contract_version", "entry_point", "execution_kind"].every(field => typeof identity[field] === "string")
    && (identity.source_sha256 === null || typeof identity.source_sha256 === "string")
    && (identity.scientific_version === null || typeof identity.scientific_version === "string")
    && ["id", "version", "slot", "contract_version", "status", "determinism"].every(field => typeof manifest[field] === "string")
    && ["inputs", "outputs", "state_reads", "state_writes", "parameters", "provides_capabilities", "requires_capabilities", "artifacts"].every(field => strings(manifest[field]))
    && record(manifest.units) && Object.values(manifest.units).every(unit => typeof unit === "string")
    && typeof source.available === "boolean" && typeof source.truncated === "boolean"
    && ["filename", "content", "reason"].every(field => source[field] === null || typeof source[field] === "string")
    && ["passed", "failed", "not_run"].includes(String(conformance.status))
    && strings(conformance.errors) && strings(conformance.warnings)
    && typeof conformance.scientific_validation_status === "string"
    && (conformance.origin === null || typeof conformance.origin === "string")
    && value.module_id === identity.module_id && manifest.id === identity.module_id
    && manifest.version === identity.module_version && manifest.slot === identity.slot && manifest.contract_version === identity.contract_version;
}
export function isAuthorDraftResolution(value: unknown): value is AuthorDraftResolution {
  if (!record(value) || value.schema_version !== "value.study-draft-resolution/v1" || typeof value.valid !== "boolean"
    || !record(value.compatible_modules) || !record(value.maturity) || !Array.isArray(value.maturity.acknowledgements_required)) return false;
  const issue = (item: unknown) => record(item) && typeof item.code === "string" && typeof item.message === "string" && typeof item.scope === "string";
  return Array.isArray(value.errors) && value.errors.every(issue) && Array.isArray(value.warnings) && value.warnings.every(issue)
    && Object.values(value.compatible_modules).every(options => Array.isArray(options) && options.every(option => record(option) && typeof option.id === "string" && typeof option.compatible === "boolean"))
    && value.maturity.acknowledgements_required.every(item => record(item) && ["key", "id", "version", "maturity", "acknowledgement"].every(field => typeof item[field] === "string"));
}
