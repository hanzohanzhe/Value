"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useRef, useState } from "react";
import "./RunReproductionPanel.css";
import { useT } from "../../i18n/LocaleProvider";

type Report = {
  schema_version: "value.run-reproduction-capability/v1";
  run_id: string;
  assessment: "verified_recorded_inputs_and_modules" | "blocked" | "unavailable";
  checks: Record<string, string>;
  facts: { snapshot_id?: string; input_tree_sha256?: string; recorded_data_object_count?: number; present_data_object_count?: number; annual_checkpoint_file_count?: number; recorded_modules?: Array<{ module_id: string; module_version: string }> };
  blocking_reasons: string[];
  limitations: string[];
  metadata_artifacts: Array<{ path: string; download_url: string }>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isReport(value: unknown): value is Report {
  if (!isRecord(value) || value.schema_version !== "value.run-reproduction-capability/v1"
    || typeof value.run_id !== "string"
    || !["verified_recorded_inputs_and_modules", "blocked", "unavailable"].includes(String(value.assessment))
    || !isRecord(value.checks) || !isRecord(value.facts)) return false;
  if (!["frozen_input_hashes", "current_module_compatibility", "snapshot_verification"].every(
    field => typeof (value.checks as Record<string, unknown>)[field] === "string")) return false;
  const facts = value.facts;
  if (!["snapshot_id", "input_tree_sha256"].every(field => facts[field] == null || typeof facts[field] === "string")
    || !["recorded_data_object_count", "present_data_object_count", "annual_checkpoint_file_count"].every(
      field => facts[field] === undefined || (typeof facts[field] === "number" && Number.isSafeInteger(facts[field]) && facts[field] >= 0))) return false;
  if (facts.recorded_modules !== undefined && (!Array.isArray(facts.recorded_modules)
    || !facts.recorded_modules.every(module => isRecord(module) && typeof module.module_id === "string" && typeof module.module_version === "string"))) return false;
  return Array.isArray(value.blocking_reasons) && value.blocking_reasons.every(reason => typeof reason === "string")
    && Array.isArray(value.limitations) && value.limitations.every(item => typeof item === "string")
    && Array.isArray(value.metadata_artifacts) && value.metadata_artifacts.every(artifact => isRecord(artifact)
      && typeof artifact.path === "string" && typeof artifact.download_url === "string"
      && artifact.download_url.startsWith(`/api/runs/${value.run_id}/artifacts/`));
}

export default function RunReproductionPanel({ runId }: { runId: string }) {
  const t = useT();
  const [result, setResult] = useState<{ key: string; report?: Report; error?: string }>();
  const [loadingKey, setLoadingKey] = useState<string>();
  const generation = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const key = runId;
  useEffect(() => {
    generation.current += 1;
    controller.current?.abort();
    return () => { generation.current += 1; controller.current?.abort(); };
  }, [key]);
  async function check() {
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    const attempt = ++generation.current;
    setLoadingKey(key);
    setResult(undefined);
    try {
      const response = await apiFetch(apiUrl(`runs/${encodeURIComponent(runId)}/reproduction-capability`), { signal: abort.signal });
      const body: unknown = await response.json();
      if (!response.ok) throw new Error(isRecord(body) && typeof body.error === "string" ? body.error : t("reproduction.requestFailed", { status: response.status }));
      if (!isReport(body)) throw new Error(t("reproduction.invalidResponse"));
      if (body.run_id !== runId) throw new Error(t("reproduction.identityMismatch"));
      if (generation.current === attempt) setResult({ key, report: body });
    } catch (error) {
      if (!abort.signal.aborted && generation.current === attempt) setResult({ key, error: error instanceof Error ? error.message : t("reproduction.failed") });
    } finally {
      if (generation.current === attempt) setLoadingKey(undefined);
    }
  }
  const active = result?.key === key ? result : undefined;
  const report = active?.report;
  const checking = loadingKey === key;
  const status = t(report?.assessment === "verified_recorded_inputs_and_modules" ? "reproduction.status.verified" : report?.assessment === "blocked" ? "reproduction.status.blocked" : "reproduction.status.noSnapshot");
  return <details key={key} className="run-reproduction-panel">
    <summary>{t("reproduction.summary")}</summary>
    <p>{t("reproduction.intro")}</p>
    <button type="button" disabled={checking} onClick={check}>{t(checking ? "reproduction.checking" : "reproduction.check")}</button>
    <div aria-live="polite">
      {active?.error && <p role="alert">{t("reproduction.error", { error: active.error })}</p>}
      {report && <>
        <p><strong>{status}</strong></p>
        <p>{t("reproduction.checks", { hashes: t(report.checks.frozen_input_hashes === "verified" ? "reproduction.verified" : "reproduction.notVerified"), modules: t(report.checks.current_module_compatibility === "verified" ? "reproduction.verified" : "reproduction.notVerified") })}</p>
        {report.facts.recorded_data_object_count !== undefined && <p>{t("reproduction.objects", { recorded: report.facts.recorded_data_object_count, present: report.facts.present_data_object_count })}</p>}
        <p>{t("reproduction.checkpoints", { count: report.facts.annual_checkpoint_file_count ?? 0 })}</p>
        {!!report.blocking_reasons.length && <ul>{report.blocking_reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul>}
        <ul>{report.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
        <details className="run-reproduction-details"><summary>{t("reproduction.details")}</summary>
        {report.facts.snapshot_id && <p className="run-reproduction-identity">{t("reproduction.snapshot", { id: report.facts.snapshot_id })}</p>}
        {!!report.facts.recorded_modules?.length && <ul>{report.facts.recorded_modules.map((module, index) => <li key={`${module.module_id}-${index}`}>{module.module_id} · {module.module_version}</li>)}</ul>}
        {!!report.metadata_artifacts.length && <><p>{t("reproduction.metadata")}</p><ul>{report.metadata_artifacts.map(artifact => <li key={artifact.path}><a href={artifact.download_url} target="_blank" rel="noreferrer">{artifact.path}</a></li>)}</ul></>}
        </details>
      </>}
    </div>
  </details>;
}
