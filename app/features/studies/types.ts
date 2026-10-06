import type { ZonalSolverContract } from "../network/networkRedispatch";
import type { RunMode } from "../runs/types";

export type Module = {
  id: string; name: string; kind: "psm" | "cem" | "system"; slot: string;
  version: string; scientific_version?: string; contract_version?: string;
  status: "ready" | "experimental" | "not_evaluated" | "extracting"; order?: number; description?: string; origin?: "built_in" | "local_bundle";
  inputs: string[]; outputs: string[]; implementation?: string; provides_capabilities?: string[]; requires_capabilities?: string[];
};
export type ModuleInstallation = {
  module_id: string; name: string; module_version: string; scientific_version?: string | null;
  slot: string; contract_version: string; implementation: string; bundle_sha256: string;
  source_sha256?: string; installed_at: string; enabled: boolean; execution_boundary: string;
  scientific_validation_status: string; conformance: { status: "passed" | "failed"; errors: string[]; warnings: string[] };
};
export type Slot = { role: string; group: string; label: string; formats: string[]; supported_formats?: string[]; required: boolean; unit?: string; source?: "base" | "extension"; owner_extension?: string | null; capability?: string; time_semantics?: string; coordinate_semantics?: string; adapter_contract?: string; validation_rules?: Record<string, unknown>; template_available?: boolean };
export type ExtensionParameter = { name: string; value_type: "boolean" | "integer" | "number" | "string"; default: unknown; title: string; description: string; visibility: "basic" | "advanced"; unit?: string | null; minimum?: number | null; maximum?: number | null; enum?: unknown[] };
export type Extension = {
  id: string; name: string; version: string; licence: string; namespace: string;
  maturity: "ready" | "experimental" | "not_evaluated"; enabled: boolean;
  origin: "built_in" | "local_bundle"; provided_capabilities: string[]; required_capabilities: string[];
  composed_module_ids: string[]; data_roles: Slot[]; parameters: ExtensionParameter[];
  artifacts: { artifact_type: string; media_type: string; schema_version: string; summary_fields: string[] }[];
  hooks: { hook: string; implementation: string }[]; manifest_sha256: string;
  installation?: { bundle_sha256?: string; installed_at?: string; enabled?: boolean } | null;
};
export type ExtensionInstallation = {
  extension_id: string; name?: string; version: string; namespace: string;
  bundle_sha256: string; manifest_sha256?: string; installed_at: string; enabled: boolean;
  licence?: string; maturity?: string; provided_capabilities?: string[];
  required_capabilities?: string[]; composed_module_ids?: string[];
  installation_boundary?: string; installation_path?: string;
  conformance?: { status: string; meaning?: string };
};
export type ModuleSlot = { slot: string; required: boolean; contract_version: string; order: number; options: (Pick<Module, "id" | "name" | "version" | "status" | "description" | "provides_capabilities" | "requires_capabilities" | "origin"> & { compatible?: boolean; reason?: string | null; methodology_supported?: boolean; methodology_reason?: string | null })[] };
export type DraftIssue = { code: string; message: string; scope: string; detail?: unknown };
export type DomainPreset = { id: string; title: string; claim: string; psm_module_id: string; psm_name: string; description: string; maturity: Module["status"]; recommended_modules: Record<string, string>; required_extensions: string[]; available: boolean; unavailable_reason?: string | null };
export type DraftResolution = {
  schema_version: string; frontend_contract_version: string; valid: boolean;
  errors: DraftIssue[]; warnings: DraftIssue[]; module_slots: ModuleSlot[];
  compatible_modules: Record<string, (ModuleSlot["options"][number] & { compatible: boolean; reason?: string | null })[]>;
  system_domains: DomainPreset[]; active_dataset_slots: Slot[];
  data_readiness: { required: number; available: number; missing_roles: string[] };
  effective_extension_parameters: Record<string, unknown>;
  maturity: { acknowledgement_contract: string; acknowledgements_required: { key: string; kind: string; id: string; version: string; maturity: string; acknowledgement: string }[] };
  graph_preview?: { graph_sha256: string; modules: Record<string, { module_id: string; module_version: string; contract_version: string }>; extension_graph?: { extensions: { id: string; version: string }[]; parameters: Record<string, unknown> } } | null;
  graph_sha256?: string | null;
  /** X0 S8: the resolved methodology of the draft, with whitelist violations and reference deviations. */
  methodology?: { profile_id: string; label: string; frozen: boolean; violations?: { sub_reason?: string; detail?: string }[]; reference_deviations?: unknown[] } | null;
};
export type MarketConfiguration = {
  network_pack_id?: string;
  zonal_demand_mode?: "" | "scenario_scaled_zonal_shares" | "network_pack_absolute_demand";
  ledger_detail?: "off" | "summary" | "full";
};
export type StudyForm = {
  name: string; purpose: string; start_year: number; end_year: number;
  modules: Record<string, string>; selected_extensions: string[];
  extension_parameters: Record<string, unknown>;
  maturity_acknowledgements: Record<string, string>;
  market_configuration: MarketConfiguration;
  solver_contract?: ZonalSolverContract;
};
export type Binding = { role?: string; filename: string; uri?: string; format?: string; bytes: number; sha256: string; imported_at: string; binding_revision?: string; unit?: string; licence?: string; source_url?: string; owner_extension?: string; capability?: string; validation?: { status: string; warnings?: string[]; details?: Record<string, unknown> } };
export type DataPack = {
  id: string; name: string; country: string; timezone: string; bindings: Record<string, Binding>;
  required_count: number; bound_required_count: number; valid_required_count: number;
  binding_issues: Record<string, string>; complete: boolean;
  manifest_sha256?: string; data_pack_type?: string;
  copy_origin?: { source_data_pack_id: string; source_manifest_sha256: string; created_at: string };
  teaching_only?: boolean; allowed_run_modes?: RunMode[];
  /** P0-5a S9 cached layer summary (spec 11.2). */
  plausibility_status?: import("../data/dataPackValidation.ts").CachedValidationStatus;
  installation?: { bundle_sha256: string; bundle_bytes: number; installed_at: string; rights_files: string[]; installation_boundary: string };
};
export type FrozenRecoveryOrigin = {
  recovery_mode: "strict" | "migration"; source_run_id: string; source_snapshot_id: string;
  required_mode: string; scope: { mode: string; start_year: number; end_year: number; periods_per_year: number };
  accepted_execution_identity_sha256: string;
};
export type Project = {
  id: string; name: string; data_pack_id: string; start_year: number; end_year: number;
  modules: Record<string, string>; parameters?: Record<string, unknown>;
  runtime_options?: Record<string, unknown>; updated_at: string;
  purpose?: string; selected_extensions?: string[]; extension_parameters?: Record<string, unknown>;
  maturity_acknowledgements?: Record<string, string>; module_resolution_graph?: { graph_sha256?: string };
  revision_sha256?: string; revision_number?: number; parent_revision_sha256?: string;
  /** X0 S11: why the latest revision was written ("user-save", "code-identity-upgrade", …). */
  revision_reason?: string;
  market_configuration?: MarketConfiguration;
  solver_contract?: ZonalSolverContract;
  extensions?: Record<string, unknown> & { frozen_recovery?: FrozenRecoveryOrigin };
  linked_run_count?: number;
  derivation?: { schema_version: string; intent: "reproduce" | "data" | "edit_module"; source_study_id: string; source_revision_sha256: string; source_data_pack_id: string; created_at: string; method_change?: { slot: string; source_module_id: string; module_id: string; candidate_identity_sha256: string } };
};
export type StudyTrashEntry = {
  trash_id: string; study_id: string; study_name: string; deleted_at: string;
  reason: string; reason_code: string; revision_sha256?: string;
  revision_count: number; linked_run_ids: string[]; linked_run_count: number;
  recoverable: boolean; legacy?: boolean;
};
export type ParameterDefinition = {
  id: string; group: string; value_type: "boolean" | "integer" | "float" | "enum" | "string";
  default: unknown; category: "fixed" | "scientific" | "runtime"; visibility: string;
  scientific_effect: string; module_owner: string; unit?: string; allowed_values: unknown[];
  minimum?: number; maximum?: number; data_pack_role?: string; experimental?: boolean;
};
