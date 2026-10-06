"use client";
import { apiUrl } from "../shared/api";
import { useEffect, useId, useRef, useState } from "react";
import type { FrozenRecoveryCreated, FrozenRecoveryMode, FrozenRecoveryReview } from "./frozenInputRecoveryTypes";
import "./frozen-input-recovery.css";

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
function solverSummary(value: unknown): string {
  if (!record(value)) return "未记录";
  const version = typeof value.contract_version === "string" ? value.contract_version.slice(0, 100) : "版本未记录";
  const ceiling = record(value.validated_ceilings) ? value.validated_ceilings.primary_bid_cost_gbp : undefined;
  return `${version}${typeof ceiling === "number" && Number.isFinite(ceiling) && ceiling > 0 ? ` · 主目标 allowance £${ceiling}` : ""}`;
}
function moduleSummary(value: unknown): string {
  if (!record(value)) return "未记录";
  const identities: string[] = [];
  if (record(value.modules)) for (const row of Object.values(value.modules)) {
    if (record(row) && typeof row.module_id === "string") identities.push(`${row.module_id.slice(0, 100)}@${typeof row.module_version === "string" ? row.module_version.slice(0, 40) : "版本未记录"}`);
  }
  if (record(value.extension_graph) && Array.isArray(value.extension_graph.extensions)) for (const row of value.extension_graph.extensions) {
    if (record(row) && typeof row.id === "string") identities.push(`${row.id.slice(0, 100)}@${typeof row.version === "string" ? row.version.slice(0, 40) : "版本未记录"}`);
  }
  return identities.length ? `${identities.slice(0, 6).join("、")}${identities.length > 6 ? `，另 ${identities.length - 6} 项` : ""}` : "没有可读的模块版本记录";
}
function changeSummary(change: FrozenRecoveryReview["changes"][number]): { label: string; detail: string } {
  const labels: Record<string, string> = { solver_contract: "求解政策", module_resolution_graph: "模块/扩展声明", maturity_acknowledgements: "实验版本确认", source_sha256: "源码身份", environment_sha256: "环境身份" };
  const label = labels[change.field] ?? `配置：${change.field.slice(0, 80)}`;
  if (change.field === "solver_contract") return { label, detail: `旧：${solverSummary(change.recorded)}；新：${solverSummary(change.current)}` };
  if (change.field === "module_resolution_graph") return { label, detail: `旧：${moduleSummary(change.recorded)}；新：${moduleSummary(change.current)}` };
  return { label, detail: "记录值与当前值不同；完整记录可在下方展开核对。" };
}
// R-D4 (four-role report, round R1-5): both requests take about 20 s; say so while they run.
const FROZEN_REVIEW_PROGRESS = "正在核对冻结输入与执行身份，通常需要约 20 秒。";
const FROZEN_CREATE_PROGRESS = "正在创建独立 Study，通常需要约 20 秒。关闭页面后服务端仍会完成创建：之后请在 Studies 中查找它，不要再次创建。";
async function json(response: Response): Promise<unknown> { const value: unknown = await response.json(); if (!response.ok) throw new Error(record(value) && typeof value.error === "string" ? value.error : "冻结输入请求失败，请重新核对来源 Run。"); return value; }

export default function FrozenInputRecoveryPanel(props: FrozenInputRecoveryPanelProps) {
  return <RecoveryForm key={JSON.stringify([props.runId, Boolean(props.disabled)])} {...props} />;
}

function RecoveryForm({ runId, disabled = false, onStudyCreated }: FrozenInputRecoveryPanelProps) {
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
  const [messageState, setMessage] = useState<{ key: string; value: string } | null>(null);
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
    try { const value = await json(await fetch(apiUrl(`runs/${encodeURIComponent(runId)}/frozen-recovery/review`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ recovery_mode: mode }), signal: abort.signal })); if (!live(abort, attempt)) return; if (!validReview(value) || value.source_run_id !== runId || value.recovery_mode !== mode) throw new Error("审阅报告与当前来源 Run 或方式不一致。"); setReport({ key: context, value }); }
    catch (reason) { if (live(abort, attempt)) setMessage({ key: context, value: reason instanceof Error ? reason.message : "冻结输入核对失败。" }); }
    finally { if (live(abort, attempt)) setActivity(null); }
  }
  async function create() {
    if (locked || submitted.current || !report?.allowed || !report.scope || confirmation !== report.review_sha256 || !name.trim() || name.trim().length > 160) return;
    submitted.current = true; const { abort, attempt } = begin("create");
    let created = false;
    try {
      const value = await json(await fetch(apiUrl(`runs/${encodeURIComponent(runId)}/frozen-recovery`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ recovery_mode: mode, review_sha256: report.review_sha256, name: name.trim(), acknowledge: true }), signal: abort.signal }));
      if (!live(abort, attempt)) return;
      if (!record(value) || value.schema_version !== "value.frozen-recovery-created/v1" || value.source_run_id !== runId || value.source_snapshot_id !== report.source_snapshot_id || value.run_started !== false || value.mode !== report.scope.mode || !record(value.project) || typeof value.project.id !== "string" || !value.project.id || value.project.id === runId || typeof value.project.name !== "string") throw new Error("创建回执身份不一致，请刷新 Study 列表核对，避免重复创建。");
      const result = value as FrozenRecoveryCreated; created = true; setReport(null); setConfirmation(null);
      setMessage({ key: context, value: "已创建独立 Study。请在 Runs 明确选择范围、Check readiness，再启动。尚未创建新 Run；未恢复年度检查点。" });
      try { await onStudyCreated(result.project.id, result.mode); } catch { if (live(abort, attempt)) setMessage({ key: context, value: `Study ${result.project.id} 已创建，但工作区未刷新。请刷新后选择它，无需再次创建。` }); }
    } catch (reason) { if (live(abort, attempt)) { setReport(null); setConfirmation(null); setMessage({ key: context, value: reason instanceof Error ? reason.message : "创建失败，请重新审阅。" }); } }
    finally { if (live(abort, attempt)) { setActivity(null); if (!created) submitted.current = false; } }
  }
  return <section className="frozen-input-recovery" aria-labelledby={`${id}-heading`} aria-busy={busy}>
    <h3 id={`${id}-heading`}>从此 Run 的冻结输入创建独立 Study</h3><p>来源 Run：<code>{runId}</code>。先核对冻结规范数据和执行身份；不会自动运行或恢复检查点。</p>
    <label><span>核对方式</span><select disabled={disabled || activity?.kind === "create"} value={mode} onChange={event => { clearReview(); setMode(event.target.value as FrozenRecoveryMode); }}><option value="strict">严格核对当前源码与环境</option><option value="migration">显式按当前方法迁移</option></select></label>
    <p>{mode === "strict" ? "严格方式核对当前本地源码和环境与已归档执行记录。通过核对不表示归档可独立运行；历史证据限制以审阅报告为准。" : "迁移保留冻结规范数据，使用当前方法重新计算。科学政策或方法差异须明确审阅；不恢复旧检查点，也不代表数值相同。"}</p>
    <button type="button" className="secondary" disabled={locked} onClick={() => void review()}>核对冻结输入与执行身份</button>
    {busy && activity?.kind === "review" && <p role="status" className="frozen-recovery-progress">{FROZEN_REVIEW_PROGRESS}</p>}
    {report && <><h4>{report.allowed ? "核对完成，等待明确创建" : "当前方式存在阻断"}</h4><p>输入完整性：{report.input_integrity} · 规范角色 {report.canonical_role_count}<br />来源快照：<code>{report.source_snapshot_id ?? "缺失"}</code></p><p>核对范围：{report.scope ? `${report.scope.start_year}–${report.scope.end_year} · 每年 ${report.scope.periods_per_year} 时段 · ${report.scope.mode}` : "未记录范围"}</p>{report.changes.length > 0 ? <ul className="frozen-recovery-changes">{report.changes.map((change, index) => { const summary = changeSummary(change); return <li key={index}><b>{summary.label}</b><span>{summary.detail}</span></li>; })}</ul> : <p>报告未列出执行身份变更。</p>}<details><summary>完整身份与差异记录</summary><pre>{JSON.stringify({ scope: report.scope, source_execution_identity_sha256: report.source_execution_identity_sha256, current_execution_identity_sha256: report.current_execution_identity_sha256, changes: report.changes }, null, 2)}</pre></details>{report.missing_evidence.length > 0 && <><b>缺失证据</b><ul>{report.missing_evidence.map((item, index) => <li key={index}>{item}</li>)}</ul></>}{report.blocking_reasons.length > 0 && <ul>{report.blocking_reasons.map((item, index) => <li key={index}>{item}</li>)}</ul>}<ul>{report.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>{report.allowed && <><label><span>新 Study 名称</span><input maxLength={160} disabled={locked} value={name} onChange={event => { setName(event.target.value); setConfirmation(null); }} /></label><label className="frozen-recovery-confirm"><input type="checkbox" disabled={locked} checked={confirmation === report.review_sha256} onChange={event => setConfirmation(event.target.checked ? report.review_sha256 : null)} /><span>我已审阅此来源 Run、执行身份差异与缺失证据，确认以{mode === "strict" ? "严格核对" : "当前方法迁移"}方式只创建独立 Study，不启动运行。</span></label><button type="button" className="primary" disabled={locked || confirmation !== report.review_sha256 || !name.trim() || name.trim().length > 160} onClick={() => void create()}>确认创建独立 Study</button></>}</>}
    <details className="frozen-archive-instructions">
      <summary>Run with the archived method</summary>
      <p>当前方法已变化时，可在同一 Linux 宿主准备独立归档工作区。缺少归档会拒绝；不会自动启动 Run，也不恢复旧检查点。</p>
      <p>在终端进入源码根目录（安装版为安装目录的 <code>app</code>），替换以下绝对路径占位符。先运行 review，核对报告，并将报告的 review_sha256 替换到 prepare 命令；源身份变化须重新审阅。只在信任归档源码后运行 prepare，<code>--acknowledge-code</code> 表示明确接受执行该源码。</p>
      <pre aria-label="Review archived workspace command">{archivedReview}</pre>
      <pre aria-label="Prepare archived workspace command">{archivedPrepare}</pre>
      <p>prepare 复制历史源码、Python 与输入，保存独立 Study，复用当前发行界面。准备后先停止当前实例，再按生成说明 start 新工作区；两者共用 8766 端口。进入新工作区后仍须 Check readiness 并明确启动 Run。</p>
      <p>宿主库与 locale 仍依赖原 Linux 环境；不表示完全离线或跨平台恢复。<a href="/README.md" target="_blank" rel="noreferrer">Read me 原文</a></p>
    </details>
    {busy && activity?.kind === "create" && <p role="status" className="frozen-recovery-progress">{FROZEN_CREATE_PROGRESS}</p>}
    {messageState?.key === context && <p role="status">{messageState.value}</p>}
  </section>;
}
