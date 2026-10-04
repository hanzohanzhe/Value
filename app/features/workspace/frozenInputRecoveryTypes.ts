export type FrozenRecoveryMode = "strict" | "migration";
export type FrozenRecoveryReview = {
  schema_version: "value.frozen-recovery-review/v1";
  source_run_id: string; source_snapshot_id: string | null; recovery_mode: FrozenRecoveryMode;
  review_sha256: string; allowed: boolean; input_integrity: "verified" | "blocked";
  scope: { mode: string; start_year: number; end_year: number; periods_per_year: number } | null;
  canonical_role_count: number; source_execution_identity_sha256: string | null; current_execution_identity_sha256: string | null;
  missing_evidence: string[]; changes: { field: string; recorded: unknown; current: unknown }[];
  blocking_reasons: string[]; limitations: string[];
};
export type FrozenRecoveryCreated = {
  schema_version: "value.frozen-recovery-created/v1"; source_run_id: string; source_snapshot_id: string | null;
  project: { id: string; name: string }; run_started: false; mode: string;
};
