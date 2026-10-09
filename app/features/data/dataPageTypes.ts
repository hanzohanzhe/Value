// Data page payloads (moved from app/page.tsx in P1 W3).
export type DataPreview = { schema_version: string; role: string; status: string; format?: string; bytes?: number; source_sha256?: string; filename?: string; unit?: string; definition?: string; capability?: string; time_semantics?: string; columns?: string[]; sampled_rows?: number; duplicate_sample_identities?: number; timestamp_sample?: { first?: string | null; last?: string | null }; numeric_ranges?: Record<string, { minimum: number; maximum: number }>; top_level_keys?: string[]; array_counts?: Record<string, number>; sample?: unknown; reason?: string };
export type ResearchSuiteInstallation = {
  suite_id: string; suite_sha256: string; suite_bytes: number;
  component_pack_ids: string[]; component_bundle_sha256: string[];
  study_ids: string[]; rights_files: string[]; installation_boundary: string;
  idempotent: boolean;
};
export type ResearchSuiteSummary = {
  suiteId: string; suiteSha256: string;
  components: { id: string; sha256: string }[];
  studyIds: string[]; idempotent: boolean; runStarted: false;
};
