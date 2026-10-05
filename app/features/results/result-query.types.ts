export type ResultSourceChoice = "auto" | "sqlite" | "compact";
export type ResultResolution = "annual" | "half_hour";
export type CurtailmentQueryItem = {
  year: number; period?: number; period_id?: string; period_count: number;
  available_mwh: number | null; economic_mwh: number | null;
  forecast_added_mwh: number | null; forecast_avoided_mwh: number | null;
  redispatch_added_mwh: number | null; redispatch_avoided_mwh: number | null;
  redispatch_net_mwh: number | null; total_mwh: number | null; rate: number | null;
  identity_residual_mwh: number | null; aggregate_tolerance_mwh: number | null;
  realised_input_sha256?: string | null;
};
export type CurtailmentQueryResponse = {
  schema_version: "value.result-query/v1";
  family: "vre-curtailment";
  contract_version: "value.vre-curtailment-attribution/v2";
  status: "reconciled" | "unavailable" | "withheld" | "invalid";
  reason_code: string | null;
  /** Older wording of an annual-coverage verdict (reason_code carries the precise code). */
  legacy_reason_code?: string | null;
  identity: {
    run_id: string; requested_run_id: string; recorded_run_id: string | null;
    study_id: string | null; study_revision: string | null; input_snapshot_id: string | null;
    data_pack_id: string | null; network_pack_id: string | null; initial_state_sha256: string | null;
    module_resolution_graph_sha256: string | null; module_identities: unknown;
    missing_fields?: string[];
    attribution_method_id?: string; counterfactual_realised_input_set_sha256?: string;
  };
  source: { kind: "sqlite" | "compact"; requested: ResultSourceChoice; artifact_path: string;
    artifact_sha256: string | null; original_schema_version: string | null; trace_level: string | null };
  scope: { resolution: ResultResolution; year: number | null; period_from: number | null; period_to: number | null };
  capabilities: {
    available_resolutions: ResultResolution[];
    available_dimensions: string[];
    unavailable_dimensions: string[];
  };
  limit: number; offset: number; total: number; count: number; has_more: boolean;
  items: CurtailmentQueryItem[];
};

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function isCurtailmentQueryResponse(value: unknown): value is CurtailmentQueryResponse {
  if (!isRecord(value) || value.schema_version !== "value.result-query/v1"
    || value.family !== "vre-curtailment" || value.contract_version !== "value.vre-curtailment-attribution/v2"
    || !["reconciled", "unavailable", "withheld", "invalid"].includes(String(value.status))
    || !(value.reason_code === null || typeof value.reason_code === "string")
    || !isRecord(value.identity) || typeof value.identity.run_id !== "string"
    || !isRecord(value.source) || !["sqlite", "compact"].includes(String(value.source.kind))
    || !isRecord(value.scope) || !["annual", "half_hour"].includes(String(value.scope.resolution))
    || !isRecord(value.capabilities) || !Array.isArray(value.items)) return false;
  const caps = value.capabilities;
  const scope = value.scope;
  if (typeof value.identity.requested_run_id !== "string"
    || !["auto", "sqlite", "compact"].includes(String(value.source.requested))
    || typeof value.source.artifact_path !== "string"
    || !(value.source.artifact_sha256 === null || typeof value.source.artifact_sha256 === "string")
    || !["year", "period_from", "period_to"].every(field => scope[field] === null || Number.isSafeInteger(scope[field]))) return false;
  if (!Array.isArray(caps.available_resolutions) || !caps.available_resolutions.every(item => ["annual", "half_hour"].includes(String(item)))
    || !Array.isArray(caps.available_dimensions) || !caps.available_dimensions.every(item => typeof item === "string")
    || !Array.isArray(caps.unavailable_dimensions) || !caps.unavailable_dimensions.every(item => typeof item === "string")) return false;
  const pagination = value;
  if (!["limit", "offset", "total", "count"].every(field => Number.isSafeInteger(pagination[field]) && Number(pagination[field]) >= 0)
    || typeof pagination.has_more !== "boolean") return false;
  const metrics = ["available_mwh", "economic_mwh", "forecast_added_mwh", "forecast_avoided_mwh", "redispatch_added_mwh", "redispatch_avoided_mwh", "redispatch_net_mwh", "total_mwh", "rate", "identity_residual_mwh", "aggregate_tolerance_mwh"];
  return value.items.every(item => isRecord(item) && Number.isSafeInteger(item.year)
    && Number.isSafeInteger(item.period_count) && Number(item.period_count) >= 0
    && metrics.every(field => item[field] === null || (typeof item[field] === "number" && Number.isFinite(item[field])))
    && (scope.resolution !== "half_hour" || (Number.isSafeInteger(item.period) && typeof item.period_id === "string")));
}
