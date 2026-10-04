import type { SourceStudyStatus } from "../learn/studyLifecycle";
import type { TraceProfile } from "../market/TraceCoverageNotice";

export type RunMode = "smoke" | "two_year_smoke" | "validation_24h" | "validation_168h" | "value_101_day" | "two_year" | "full";
export type PlanningBreakdown = Record<string, Record<string, { projects: number; capacity_mw: number }>>;
export type PlanningYear = { year: number; introduced_projects: number; accounted_projects: number; reconciled: boolean; breakdowns: PlanningBreakdown; kpis?: Record<string, { projects: number; capacity_mw: number }>; cause_breakdowns?: { event_type?: Record<string, { projects: number; capacity_mw: number }>; reason_code?: Record<string, { projects: number; capacity_mw: number }> } };
export type RunResult = { year: number; metrics: Record<string, number | string | null>; capacity_mw?: Record<string, number>; capacity_mwh?: Record<string, number | null>; planning?: Record<string, number | string> };
export type RecoveryCapability = {
  annual_resume_supported: boolean; annual_safe_boundary: string; subannual_resume_supported: boolean;
  user_message: string; state_gaps?: string[];
  latest_safe_point?: { available: boolean; year: number | null; artifact: string | null; meaning?: string };
};
export type ModelRun = {
  input_snapshot_id?: string; input_tree_sha256?: string; recorded_project_revision_sha256?: string | null;
  id: string; project_id: string; project_name: string; mode: RunMode;
  status: "queued" | "snapshotting" | "running" | "cancel_requested" | "cancelled" | "completed" | "failed" | "archived" | "deleting"; current_stage: string;
  completed_years: number; total_years: number; updated_at: string; error?: string; error_code?: string;
  results: RunResult[]; modules?: Record<string, string>;
  module_evidence?: Record<string, { version: string; actions: number; years: number[] }>;
  diagnostic?: { periods_per_year?: number; total_periods?: number; years?: number[]; purpose?: string; annual_economics_published?: boolean; scientific_results_published?: boolean; warning?: string };
  execution_status?: string; contract_validation_status?: string; scientific_validation_status?: string;
  scientific_scenario_status?: string; retained_comparison_role?: string;
  retained_numerical_comparison_status?: string;
  run_policy?: { label?: string; purpose?: string; periods_per_year?: number; total_periods?: number; annual_economics_candidate?: boolean };
  recovery?: RecoveryCapability;
  comparison_parent_run_id?: string;
  extensions?: Record<string, unknown>;
  source_study_status?: SourceStudyStatus;
};
export type PreflightIssue = { code: string; severity: "error" | "warning"; scope: string; message: string; corrective_action: string };
export type DomainMetric = { value: unknown; unit: string; definition_id: string; source_sha256?: unknown; status: string };
export type DomainSection = { status: string; claim?: string; error?: string; metrics?: Record<string, DomainMetric>; source_sha256?: unknown; [key: string]: unknown };
export type DomainReadiness = {
  schema_version: string; status: string; ready: boolean; preview_periods: number;
  requested_periods: number; bounded: boolean; sections: Record<string, DomainSection>;
  issues: (PreflightIssue & { control?: string })[];
};
export type PreflightReport = {
  project_id?: string; project_revision_sha256?: string; data_pack_id?: string;
  accepted: boolean; mode: RunMode;
  errors: PreflightIssue[]; warnings: PreflightIssue[];
  checks?: { domain_readiness?: DomainReadiness; [key: string]: unknown };
  estimates: { periods?: number; disk_bytes?: number; runtime_seconds?: number; runtime_basis?: string; peak_memory_bytes?: number; memory_basis?: string; data_scale?: { operating_assets?: number; planning_projects?: number } };
  resource_readiness?: ResourceReadiness | null;
};
export type ResourceReadiness = {
  trace_profile: TraceProfile;
  run_context_sha256: string;
  year_context_sha256: string;
  calibration_key: { data_fingerprint?: string; module_fingerprint?: string; solver_fingerprint?: string; clock_fingerprint?: string; [key: string]: unknown };
  calibration_basis: { source?: string; calibration_periods?: number; [key: string]: unknown };
  free_space_observation: { free_bytes: number; target_volume_capacity_bytes?: number | null };
  quota_decision: { accepted: boolean; reason_codes?: string[]; errors?: { corrective_actions?: string[] }[] };
  selected_output_root: string;
  estimate: { persisted_bytes: number; temporary_bytes: number; reserve_bytes: number; required_bytes: number; runtime_seconds: number; trace_profile: TraceProfile };
};
export type FrozenInputSnapshot = {
  snapshot_id?: string; state?: string; input_tree_sha256?: string;
  pack_manifest_sha256?: string;
  network_pack_id?: string;
  network_pack_manifest_sha256?: string;
  modules?: { slot: string; module_id: string; module_version: string; contract_version: string; source_sha256: string }[];
};
