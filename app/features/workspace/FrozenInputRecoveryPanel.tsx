"use client";
import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useId, useRef, useState } from "react";
import type { FrozenRecoveryCreated, FrozenRecoveryMode, FrozenRecoveryReview } from "./frozenInputRecoveryTypes";
import "./frozen-input-recovery.css";
import { useT } from "../../i18n/LocaleProvider";
import { LocalizedError, messageOf, showMessage, type LocalizedMessage } from "../shared/localizedMessage.ts";
import type { MessageKey, Translate } from "../../i18n/index.ts";

export type FrozenInputRecoveryPanelProps = { runId: string; disabled?: boolean; onStudyCreated: (projectId: string, mode: string) => Promise<void> | void };
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const hash = (value: unknown): value is string => typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
const nullableHash = (value: unknown) => value === null || hash(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === "string");
const positive = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value > 0;
function validReview(value: unknown): value is FrozenRecoveryReview {
  if (!record(value) || value.schema_version !== "value.frozen-recovery-review/v1" || typeof value.source_run_id !== "string" || !(value.source_snapshot_id === null || typeof value.source_snapshot_id === "string") || !["strict", "migration"].includes(String(value.recovery_mode)) || !hash(value.review_sha256) || typeof value.allowed !== "boolean" || !["verified", "blocked"].includes(String(value.input_integrity)) || !nullableHash(value.source_execution_identity_sha256) || !nullableHash(value.current_execution_identity_sha256) || typeof value.canonical_role_count !== "number" || !Number.isSafeInteger(value.canonical_role_count) || value.canonical_role_count < 0) return false;
  const scope = value.scope;
  if (!(scope === null || (record(scope) && typeof scope.mode === "string" && scope.mode.length > 0 && positive(scope.start_year) && positive(scope.end_year) && scope.end_year >= scope.start_year && positive(scope.periods_per_year)))) return false;
  return strings(value.missing_evidence) && strings(value.blocking_reasons) && strings(value.limitations) && Array.isArray(value.changes) && value.changes.every(change => record(change) && typeof change.field === "string" && Object.hasOwn(change, "recorded") && Object.hasOwn(change, "current")) && (!value.allowed || (value.input_integrity === "verified" && value.source_snapshot_id !== null && scope !== null && value.blocking_reasons.length === 0));
}
function shellQuote(value: string): string { return "'" + value.replaceAll("'", "'\"'\"'") + "'"; }
function solverSummary(t: Translate, value: unknown): string {
  if (!record(value)) return t("frozen.notRecorded");
  const version = typeof value.contract_version === "string" ? value.contract_version.slice(0, 100) : t("frozen.versionNotRecorded");
  const ceiling = record(value.validated_ceilings) ? value.validated_ceilings.primary_bid_cost_gbp : undefined;
  return `${version}${typeof ceiling === "number" && Number.isFinite(ceiling) && ceiling > 0 ? t("frozen.allowance", { amount: ceiling }) : ""}`;
}
function moduleSummary(t: Translate, value: unknown): string {
  if (!record(value)) return t("frozen.notRecorded");
  const identities: string[] = [];
  if (record(value.modules)) for (const row of Object.values(value.modules)) {
    if (record(row) && typeof row.module_id === "string") identities.push(`${row.module_id.slice(0, 100)}@${typeof row.module_version === "string" ? row.module_version.slice(0, 40) : t("frozen.versionNotRecorded")}`);
  }
  if (record(value.extension_graph) && Array.isArray(value.extension_graph.extensions)) for (const row of value.extension_graph.extensions) {
    if (record(row) && typeof row.id === "string") identities.push(`${row.id.slice(0, 100)}@${typeof row.version === "string" ? row.version.slice(0, 40) : t("frozen.versionNotRecorded")}`);
  }
  return identities.length ? `${identities.slice(0, 6).join(t("frozen.moduleJoin"))}${identities.length > 6 ? t("frozen.moreModules", { count: identities.length - 6 }) : ""}` : t("frozen.noModules");
}
function changeSummary(t: Translate, change: FrozenRecoveryReview["changes"][number]): { label: string; detail: string } {
  const labels: Record<string, MessageKey> = { solver_contract: "frozen.change.solver", module_resolution_graph: "frozen.change.modules", maturity_acknowledgements: "frozen.change.maturity", source_sha256: "frozen.change.source", environment_sha256: "frozen.change.environment" };
  const key = labels[change.field];
  const label = key ? t(key) : t("frozen.change.config", { field: change.field.slice(0, 80) });
  if (change.field === "solver_contract") return { label, detail: t("frozen.change.oldNew", { recorded: solverSummary(t, change.recorded), current: solverSummary(t, change.current) }) };
  if (change.field === "module_resolution_graph") return { label, detail: t("frozen.change.oldNew", { recorded: moduleSummary(t, change.recorded), current: moduleSummary(t, change.current) }) };
  return { label, detail: t("frozen.change.differs") };
}
// R-D4 (four-role report, round R1-5): both requests take about 20 s; say so while they run
// (messages "frozen.reviewProgress" and "frozen.createProgress").
async function json(response: Response): Promise<unknown> { const value: unknown = await response.json(); if (!response.ok) throw record(value) && typeof value.error === "string" ? new Error(value.error) : new LocalizedError("frozen.requestFailed"); return value; }

export default function FrozenInputRecoveryPanel(props: FrozenInputRecoveryPanelProps) {
  return <RecoveryForm key={JSON.stringify([props.runId, Boolean(props.disabled)])} {...props} />;
}

function RecoveryForm({ runId, disabled = false, onStudyCreated }: FrozenInputRecoveryPanelProps) {
  const t = useT();
  const id = useId();
  const archivedArgs = `--run-id ${shellQuote(runId)} --data-home '/absolute/state' --destination '/absolute/new-workspace' --node '/absolute/node' --name 'Archived method Study'`;
  const archivedReview = `python3 scripts/prepare_archived_workspace.py review ${archivedArgs}`;
  const archivedPrepare = `python3 scripts/prepare_archived_workspace.py prepare ${archivedArgs} --review-sha256 'REVIEW_SHA256_FROM_REPORT' --acknowledge-code`;
  const [mode, setMode] = useState<FrozenRecoveryMode>("strict");
  const context = JSON.stringify([runId, mode]);
  const [reportState, setReport] = useState<{ key: string; value: FrozenRecoveryReview } | null>(null);
  const [name, setName] = useState("");
  const [confirmation, setConfirmation] = useState<string | null>(null);
  const [activity, setActivity] = useState<{ key: string; kind: "review" | "create" } | null>(null);
  const [messageState, setMessage] = useState<{ key: string; value: LocalizedMessage } | null>(null);
  const controller = useRef<AbortController | null>(null), sequence = useRef(0), activeContext = useRef(context), submitted = useRef(false);
  const report = reportState?.key === context ? reportState.value : null;
  const busy = activity?.key === context, locked = disabled || busy;
  useEffect(() => { activeContext.current = context; controller.current?.abort(); sequence.current += 1; submitted.current = false; return () => { controller.current?.abort(); sequence.current += 1; }; }, [context, disabled]);
  function clearReview() { controller.current?.abort(); sequence.current += 1; setReport(null); setConfirmation(null); setMessage(null); setActivity(null); }
  function begin(kind: "review" | "create") { controller.current?.abort(); const abort = new AbortController(); controller.current = abort; const attempt = ++sequence.current; setActivity({ key: context, kind }); setMessage(null); return { abort, attempt }; }
  function live(abort: AbortController, attempt: number) { return !abort.signal.aborted && sequence.current === attempt && activeContext.current === context; }
  async function review() {
    if (locked) return;
    clearReview(); submitted.current = false; const { abort, attempt } = begin("review");
    try { const value = await json(await apiFetch(apiUrl(`runs/${encodeURIComponent(runId)}/frozen-recovery/review`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ recovery_mode: mode }), signal: abort.signal })); if (!live(abort, attempt)) return; if (!validReview(value) || value.source_run_id !== runId || value.recovery_mode !== mode) throw new LocalizedError("frozen.reviewMismatch"); setReport({ key: context, value }); }
    catch (reason) { if (live(abort, attempt)) setMessage({ key: context, value: messageOf(reason, "frozen.reviewFailed") }); }
    finally { if (live(abort, attempt)) setActivity(null); }
  }
  async function create() {
    if (locked || submitted.current || !report?.allowed || !report.scope || confirmation !== report.review_sha256 || !name.trim() || name.trim().length > 160) return;
    submitted.current = true; const { abort, attempt } = begin("create");
    let created = false;
    try {
      const value = await json(await apiFetch(apiUrl(`runs/${encodeURIComponent(runId)}/frozen-recovery`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ recovery_mode: mode, review_sha256: report.review_sha256, name: name.trim(), acknowledge: true }), signal: abort.signal }));
      if (!live(abort, attempt)) return;
      if (!record(value) || value.schema_version !== "value.frozen-recovery-created/v1" || value.source_run_id !== runId || value.source_snapshot_id !== report.source_snapshot_id || value.run_started !== false || value.mode !== report.scope.mode || !record(value.project) || typeof value.project.id !== "string" || !value.project.id || value.project.id === runId || typeof value.project.name !== "string") throw new LocalizedError("frozen.receiptMismatch");
      const result = value as FrozenRecoveryCreated; created = true; setReport(null); setConfirmation(null);
      setMessage({ key: context, value: { key: "frozen.created" } });
      try { await onStudyCreated(result.project.id, result.mode); } catch { if (live(abort, attempt)) setMessage({ key: context, value: { key: "frozen.createdNotRefreshed", values: { id: result.project.id } } }); }
    } catch (reason) { if (live(abort, attempt)) { setReport(null); setConfirmation(null); setMessage({ key: context, value: messageOf(reason, "frozen.createFailed") }); } }
    finally { if (live(abort, attempt)) { setActivity(null); if (!created) submitted.current = false; } }
  }
  return <section className="frozen-input-recovery" aria-labelledby={`${id}-heading`} aria-busy={busy}>
    <h3 id={`${id}-heading`}>{t("frozen.title")}</h3><p>{t("frozen.sourceRun")}<code>{runId}</code>{t("frozen.intro")}</p>
    <label><span>{t("frozen.mode")}</span><select disabled={disabled || activity?.kind === "create"} value={mode} onChange={event => { clearReview(); setMode(event.target.value as FrozenRecoveryMode); }}><option value="strict">{t("frozen.mode.strict")}</option><option value="migration">{t("frozen.mode.migration")}</option></select></label>
    <p>{t(mode === "strict" ? "frozen.mode.strictBody" : "frozen.mode.migrationBody")}</p>
    <button type="button" className="secondary" disabled={locked} onClick={() => void review()}>{t("frozen.review")}</button>
    {busy && activity?.kind === "review" && <p role="status" className="frozen-recovery-progress">{t("frozen.reviewProgress")}</p>}
    {report && <><h4>{t(report.allowed ? "frozen.report.allowed" : "frozen.report.blocked")}</h4><p>{t("frozen.report.integrity", { integrity: report.input_integrity, count: report.canonical_role_count })}<br />{t("frozen.report.snapshot")}<code>{report.source_snapshot_id ?? t("frozen.report.snapshotMissing")}</code></p><p>{t("frozen.report.scope", { scope: report.scope ? t("frozen.report.scopeValue", { start: report.scope.start_year, end: report.scope.end_year, periods: report.scope.periods_per_year, mode: report.scope.mode }) : t("frozen.report.scopeMissing") })}</p>{report.changes.length > 0 ? <ul className="frozen-recovery-changes">{report.changes.map((change, index) => { const summary = changeSummary(t, change); return <li key={index}><b>{summary.label}</b><span>{summary.detail}</span></li>; })}</ul> : <p>{t("frozen.report.noChanges")}</p>}<details><summary>{t("frozen.report.full")}</summary><pre>{JSON.stringify({ scope: report.scope, source_execution_identity_sha256: report.source_execution_identity_sha256, current_execution_identity_sha256: report.current_execution_identity_sha256, changes: report.changes }, null, 2)}</pre></details>{report.missing_evidence.length > 0 && <><b>{t("frozen.report.missing")}</b><ul>{report.missing_evidence.map((item, index) => <li key={index}>{item}</li>)}</ul></>}{report.blocking_reasons.length > 0 && <ul>{report.blocking_reasons.map((item, index) => <li key={index}>{item}</li>)}</ul>}<ul>{report.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>{report.allowed && <><label><span>{t("frozen.name")}</span><input maxLength={160} disabled={locked} value={name} onChange={event => { setName(event.target.value); setConfirmation(null); }} /></label><label className="frozen-recovery-confirm"><input type="checkbox" disabled={locked} checked={confirmation === report.review_sha256} onChange={event => setConfirmation(event.target.checked ? report.review_sha256 : null)} /><span>{t(mode === "strict" ? "frozen.confirm.strict" : "frozen.confirm.migration")}</span></label><button type="button" className="primary" disabled={locked || confirmation !== report.review_sha256 || !name.trim() || name.trim().length > 160} onClick={() => void create()}>{t("frozen.create")}</button></>}</>}
    <details className="frozen-archive-instructions">
      <summary>{t("runs.results.archived")}</summary>
      <p>{t("frozen.archive.p1")}</p>
      <p>{t("frozen.archive.p2a")}<code>app</code>{t("frozen.archive.p2b")}<code>--acknowledge-code</code>{t("frozen.archive.p2c")}</p>
      <pre aria-label={t("frozen.archive.reviewLabel")}>{archivedReview}</pre>
      <pre aria-label={t("frozen.archive.prepareLabel")}>{archivedPrepare}</pre>
      <p>{t("frozen.archive.p3")}</p>
      <p>{t("frozen.archive.p4")}<a href="/README.md" target="_blank" rel="noreferrer">{t("frozen.archive.readme")}</a></p>
    </details>
    {busy && activity?.kind === "create" && <p role="status" className="frozen-recovery-progress">{t("frozen.createProgress")}</p>}
    {messageState?.key === context && <p role="status">{showMessage(t, messageState.value)}</p>}
  </section>;
}
