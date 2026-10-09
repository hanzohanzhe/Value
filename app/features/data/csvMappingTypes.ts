export type CsvMappingColumn = { source: string; target: string; source_unit: string | null; target_unit: string | null };
export type CsvMappingRole = {
  role: string;
  columns: { target: string; target_unit: string | null }[];
  conversion_pairs: { source_unit: string; target_unit: string; requires_fx?: boolean }[];
  single_value: boolean;
  /** P0-5a S10: source units that need an explicit EUR->GBP rate (price roles). */
  fx_required_for?: string[];
  interval_minutes?: number;
  unit_contract?: string;
  /** Spec 11.6 (S-D4): the role may declare a timestamp column, read in one of these time zones. */
  timestamp_supported?: boolean;
  time_zones?: string[];
};
/** Spec 11.6 (S-D4): the chronology layer's row-by-row check of the declared timestamps. */
export type CsvTimestampReport = {
  column: string; time_zone: string; interval_minutes: number; rows_checked: number; problem_count: number;
  /** S-低3: `row` is the CSV line (header = line 1); data_row counts data rows from 1, as the cell errors do. */
  problems: { row: number; data_row?: number; csv_line?: number; timestamp: string | null; problem: string }[];
  /** N-3: first and last stamps as UTC instants; minutes from 1 January 00:00 (0 = aligned with the model clock). */
  first_utc?: string | null; last_utc?: string | null; origin_offset_minutes?: number | null;
  /** S-中3: the day/month order used and why; hints such as "the dates may be in the other order". */
  date_order?: string; date_order_basis?: string; hints?: string[];
  /** S-低2: span of the stamps and the calendar year(s) of the data. */
  coverage?: { span_days: number; full_year: boolean; data_years: number[]; rows: number } | null;
};
/** S-中2 / S-低2: what the corrected reader's clock does with the series, and confirmations the commit needs. */
export type CsvClockPlan = { source_rows: number; periods: number; hourly_doubled: boolean; leap_day_removed: boolean; ignored_periods: number; wrapped_periods: number; note: string | null };
export type CsvAcknowledgement = { code: string; text: string };
export type CsvMappingCatalog = { schema_version: "value.data-mapping-catalog/v1"; pack_id: string; target_manifest_sha256: string; roles: CsvMappingRole[]; max_upload_bytes: number };
export type CsvMappingStage = { schema_version: "value.data-mapping-stage/v1"; stage_id: string; pack_id: string; role: string; source_sha256: string; source_bytes: number; source_columns: string[]; rows: number; target_manifest_sha256: string; expires_at: string };
export type CsvMappingReview = {
  schema_version: "value.data-mapping-review/v1"; review_id: string; stage_id: string; pack_id: string; role: string;
  valid: boolean; errors: string[]; warnings: string[]; source_sha256: string; spec_sha256: string; normalized_sha256: string | null;
  target_manifest_sha256: string; source_bytes: number; normalized_bytes: number; rows: number;
  columns: CsvMappingColumn[]; sample_rows: Record<string, unknown>[]; validation: unknown; expires_at: string;
  /** F-P05A-1: raw values of the mapped source columns for the sample rows, and the rate used. */
  source_sample_rows?: Record<string, unknown>[];
  fx?: { eur_per_gbp: number; fx_basis: string; price_year?: number } | null;
  timestamp?: CsvTimestampReport | null;
  clock?: CsvClockPlan | null;
  acknowledgements_required?: CsvAcknowledgement[];
};
export type CsvMappingCommit = { schema_version: "value.data-mapping-commit/v1"; ok: true; pack_id: string; role: string; binding: unknown; validation: unknown; manifest_sha256: string; run_started: false };
