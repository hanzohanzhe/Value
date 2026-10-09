export type DataSourceDefinition = {
  schema_version: "value.data-source-definition/v1";
  source_id: string;
  authority: string;
  semantic_role: string;
  landing_page: string;
  licence_expected: string;
  candidate_uses: string[];
  expected_media_types: string[];
};

export type SourceRevision = {
  schema_version: "value.data-source-revision/v1";
  source_id: string;
  revision_id: string;
  publication_date: string;
  landing_page: string;
  download_url: string;
  media_type: string;
  reported_licence: string;
  status: "new" | "unchanged" | "superseded" | "unavailable" | "pinned";
  object_key?: string | null;
  redistribution_decision?: "redistributable" | "pointer_only" | "local_use_only" | "needs_rights_review";
  catalogue_metadata?: Record<string, unknown>;
};

export type DataJob = {
  schema_version: "value.data-job/v1";
  job_id: string;
  operation: string;
  status: "queued" | "running" | "cancel_requested" | "cancelled" | "failed" | "completed";
  progress: number;
  result?: Record<string, unknown> | null;
  error_code?: string | null;
  error_message?: string | null;
  /** F4-05: the job record's timestamps (value.data-job/v1), for the elapsed time. */
  created_at?: string | null;
  updated_at?: string | null;
};

export type CandidateSummary = {
  candidate_id: string;
  directory_id: string;
  requested_waivers: string[];
};

export type ValidationIssue = {
  code: string;
  severity: string;
  artifact_role: string;
  message: string;
  evidence: Record<string, unknown>;
  repair: string;
  waivable: boolean;
};

export type ValidationReport = {
  schema_version: "value.data-validation-report/v1";
  candidate_id: string;
  status: string;
  issues: ValidationIssue[];
  gate_results: Record<string, string>;
};

export type CandidateReview = {
  schema_version: "value.data-candidate-review/v1";
  candidate_id: string;
  status: string;
  candidate_inventory: Array<{
    item_id: string;
    status: string;
    usable_for: string[];
    not_usable_for: string[];
    blocking_reasons: string[];
    required_actions: string[];
  }>;
  blocking_reasons: string[];
  required_actions: string[];
  artifacts: Record<string, string>;
  map_ids?: string[];
  audit_map_svg?: string;
};

export type InstalledBundle = {
  pack_id: string;
  name?: string;
  installed_at: string;
  validation: { passed: number; failed: number; total: number };
  installation_boundary: string;
};

export type SignedBundleReceipt = {
  schema_version: "value.data-signed-bundle-receipt/v1";
  network_pack_id: string;
  candidate_id: string;
  bundle_sha256: string;
  approved_by: string;
  accepted_waivers: string[];
};
