"use client";

import { apiUrl } from "../shared/api";
import { useEffect, useId, useRef, useState } from "react";
import type { CsvMappingCatalog, CsvMappingColumn, CsvMappingCommit, CsvMappingReview, CsvMappingStage } from "./csvMappingTypes";
import "./csv-mapping-editor.css";

export type CsvMappingEditorProps = {
  packId: string; manifestSha256: string; role: string;
  disabled?: boolean; readOnlyReason?: string;
  onMapped: (result: CsvMappingCommit) => Promise<void> | void;
  onBusyChange?: (busy: boolean) => void;
};
type Scoped<T> = { key: string; value: T };
const record = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const hash = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const count = (value: unknown): value is number => typeof value === "number" && Number.isSafeInteger(value) && value >= 0;
const expiry = (value: unknown): value is string => typeof value === "string" && Number.isFinite(Date.parse(value));
const token = (value: unknown): value is string => typeof value === "string" && /^[0-9a-f]{32}$/.test(value);
const listOfStrings = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === "string");
const columnIdentity = (columns: CsvMappingColumn[]) => JSON.stringify(columns.map(({ source, target, source_unit, target_unit }) => ({ source, target, source_unit, target_unit })));
const validColumns = (value: unknown): value is CsvMappingColumn[] => Array.isArray(value) && value.every((item) => record(item) && typeof item.source === "string" && typeof item.target === "string" && (item.source_unit === null || typeof item.source_unit === "string") && (item.target_unit === null || typeof item.target_unit === "string"));
async function responseJson(response: Response): Promise<Record<string, unknown>> {
  const value: unknown = await response.json();
  if (!record(value)) throw new Error("服务返回了无法核对的映射报告。");
  if (!response.ok) throw new Error(typeof value.error === "string" ? value.error : "映射请求失败，请检查文件与目标包版本。");
  return value;
}

export default function CsvMappingEditor({ packId, manifestSha256, role, disabled = false, readOnlyReason, onMapped, onBusyChange }: CsvMappingEditorProps) {
  const id = useId();
  const contextKey = JSON.stringify([packId, manifestSha256, role]);
  const [catalogState, setCatalog] = useState<Scoped<CsvMappingCatalog> | null>(null);
  const [stageState, setStage] = useState<Scoped<CsvMappingStage> | null>(null);
  const [mappingState, setMapping] = useState<Scoped<CsvMappingColumn[]> | null>(null);
  const [reviewState, setReview] = useState<(Scoped<CsvMappingReview> & { mappingKey: string }) | null>(null);
  const [messageState, setMessage] = useState<Scoped<string> | null>(null);
  const [activity, setActivity] = useState<Scoped<"upload" | "review" | "commit"> | null>(null);
  const [confirmed, setConfirmed] = useState<string | null>(null);
  const operation = useRef<AbortController | null>(null);
  const requestSequence = useRef(0);
  const currentContext = useRef(contextKey);
  const catalog = catalogState?.key === contextKey ? catalogState.value : null;
  const specification = catalog?.roles.find((item) => item.role === role);
  const stage = stageState?.key === contextKey ? stageState.value : null;
  const columns = mappingState?.key === contextKey ? mappingState.value : [];
  const mappingKey = columnIdentity(columns);
  const review = reviewState?.key === contextKey && reviewState.mappingKey === mappingKey && reviewState.value.stage_id === stage?.stage_id ? reviewState.value : null;
  const busy = activity?.key === contextKey;
  const locked = disabled || Boolean(readOnlyReason) || busy;
  const message = messageState?.key === contextKey ? messageState.value : "";

  useEffect(() => {
    currentContext.current = contextKey;
    requestSequence.current += 1;
    operation.current?.abort();
    const controller = new AbortController();
    if (disabled || readOnlyReason) return () => controller.abort();
    void fetch(apiUrl(`data-packs/${encodeURIComponent(packId)}/csv-mapping/catalog`), { signal: controller.signal }).then(responseJson).then((value) => {
      if (controller.signal.aborted || currentContext.current !== contextKey) return;
      if (value.schema_version !== "value.data-mapping-catalog/v1" || value.pack_id !== packId || value.target_manifest_sha256 !== manifestSha256 || !Array.isArray(value.roles) || !value.roles.every((item) => record(item) && typeof item.role === "string" && Array.isArray(item.columns) && item.columns.every((column) => record(column) && typeof column.target === "string" && (column.target_unit === null || typeof column.target_unit === "string")) && Array.isArray(item.conversion_pairs) && item.conversion_pairs.every((pair) => record(pair) && typeof pair.source_unit === "string" && typeof pair.target_unit === "string") && typeof item.single_value === "boolean") || typeof value.max_upload_bytes !== "number" || value.max_upload_bytes <= 0) throw new Error("映射目录与当前目标包版本不一致，请刷新目标包。");
      setCatalog({ key: contextKey, value: value as CsvMappingCatalog });
    }).catch((reason: Error) => { if (!controller.signal.aborted && currentContext.current === contextKey) setMessage({ key: contextKey, value: reason.message }); });
    return () => { controller.abort(); operation.current?.abort(); requestSequence.current += 1; onBusyChange?.(false); };
  }, [packId, manifestSha256, role, contextKey, disabled, readOnlyReason, onBusyChange]);

  function invalidateReview() {
    operation.current?.abort(); requestSequence.current += 1;
    setReview(null); setConfirmed(null); setMessage(null);
  }
  function begin(kind: "upload" | "review" | "commit") {
    operation.current?.abort();
    const controller = new AbortController(); operation.current = controller;
    const sequence = ++requestSequence.current;
    setActivity({ key: contextKey, value: kind }); setMessage(null); onBusyChange?.(true);
    return { controller, sequence };
  }
  function live(sequence: number, controller: AbortController) { return !controller.signal.aborted && requestSequence.current === sequence && currentContext.current === contextKey; }
  function finish(sequence: number, controller: AbortController) { if (live(sequence, controller)) { setActivity(null); onBusyChange?.(false); } }

  async function upload(file: File) {
    invalidateReview(); setStage(null); setMapping(null);
    if (!specification || !catalog || locked) return;
    if (!file.name.toLowerCase().endsWith(".csv") || file.size === 0 || file.size > catalog.max_upload_bytes) { setMessage({ key: contextKey, value: `请选择含标题行的非空 CSV，最多 ${Math.floor(catalog.max_upload_bytes / 1024 / 1024)} MiB。` }); return; }
    const { controller, sequence } = begin("upload");
    try {
      const value = await responseJson(await fetch(apiUrl(`data-packs/${encodeURIComponent(packId)}/csv-mapping/stages?role=${encodeURIComponent(role)}`), { method: "POST", headers: { "Content-Type": "text/csv", "X-Filename": encodeURIComponent(file.name), "X-Expected-Pack-Revision": manifestSha256 }, body: file, signal: controller.signal }));
      if (!live(sequence, controller)) return;
      if (value.schema_version !== "value.data-mapping-stage/v1" || value.pack_id !== packId || value.role !== role || value.target_manifest_sha256 !== manifestSha256 || !token(value.stage_id) || !hash(value.source_sha256) || !listOfStrings(value.source_columns) || !expiry(value.expires_at) || !count(value.rows) || !count(value.source_bytes) || value.source_bytes !== file.size) throw new Error("暂存文件身份不一致，请重新选择文件。");
      const payload = value as CsvMappingStage;
      setStage({ key: contextKey, value: payload });
      setMapping({ key: contextKey, value: specification.columns.map((column) => ({ source: "", target: column.target, source_unit: column.target_unit, target_unit: column.target_unit })) });
    } catch (reason) { if (live(sequence, controller)) setMessage({ key: contextKey, value: reason instanceof Error ? reason.message : "CSV 暂存失败。" }); }
    finally { finish(sequence, controller); }
  }
  function changeColumn(index: number, patch: Partial<CsvMappingColumn>) {
    invalidateReview();
    setMapping({ key: contextKey, value: columns.map((column, item) => item === index ? { ...column, ...patch } : column) });
  }
  async function preview(requestedAt: number) {
    invalidateReview();
    if (!stage || locked || columns.some((column) => !column.source)) return;
    if (!Number.isFinite(Date.parse(stage.expires_at)) || Date.parse(stage.expires_at) <= requestedAt) { setStage(null); setMapping(null); setMessage({ key: contextKey, value: "原始文件暂存已过期，请重新选择文件。" }); return; }
    const { controller, sequence } = begin("review");
    try {
      const value = await responseJson(await fetch(apiUrl(`data-mapping/stages/${encodeURIComponent(stage.stage_id)}/preview`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ schema_version: "value.data-mapping-preview-request/v1", source_sha256: stage.source_sha256, target_manifest_sha256: manifestSha256, columns }), signal: controller.signal }));
      if (!live(sequence, controller)) return;
      if (value.schema_version !== "value.data-mapping-review/v1" || value.pack_id !== packId || value.role !== role || value.stage_id !== stage.stage_id || value.source_sha256 !== stage.source_sha256 || value.target_manifest_sha256 !== manifestSha256 || !validColumns(value.columns) || columnIdentity(value.columns) !== mappingKey || !token(value.review_id) || typeof value.valid !== "boolean" || !listOfStrings(value.errors) || !listOfStrings(value.warnings) || (!Array.isArray(value.sample_rows) || value.sample_rows.length > 20 || !value.sample_rows.every(record)) || value.source_bytes !== stage.source_bytes || value.rows !== stage.rows || !count(value.normalized_bytes) || !hash(value.spec_sha256) || !(value.normalized_sha256 === null || hash(value.normalized_sha256)) || (value.valid && (!hash(value.normalized_sha256) || !record(value.validation))) || !expiry(value.expires_at)) throw new Error("校验报告与所审阅的文件、映射或包版本不一致，请重新校验。");
      setReview({ key: contextKey, mappingKey, value: value as CsvMappingReview });
    } catch (reason) { if (live(sequence, controller)) setMessage({ key: contextKey, value: reason instanceof Error ? reason.message : "映射校验失败。" }); }
    finally { finish(sequence, controller); }
  }
  async function commit(requestedAt: number) {
    if (!review?.valid || confirmed !== review.review_id || locked) return;
    if (!Number.isFinite(Date.parse(review.expires_at)) || Date.parse(review.expires_at) <= requestedAt) { setReview(null); setConfirmed(null); setMessage({ key: contextKey, value: "审阅报告已过期，请重新校验后确认。" }); return; }
    const { controller, sequence } = begin("commit");
    try {
      const value = await responseJson(await fetch(apiUrl(`data-mapping/reviews/${encodeURIComponent(review.review_id)}/commit`), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ schema_version: "value.data-mapping-commit-request/v1", source_sha256: review.source_sha256, spec_sha256: review.spec_sha256, normalized_sha256: review.normalized_sha256, target_manifest_sha256: manifestSha256 }), signal: controller.signal }));
      if (!live(sequence, controller)) return;
      if (value.schema_version !== "value.data-mapping-commit/v1" || value.ok !== true || value.pack_id !== packId || value.role !== role || value.run_started !== false || !hash(value.manifest_sha256) || !record(value.binding) || value.binding.sha256 !== review.normalized_sha256 || !record(value.binding.mapping_provenance) || value.binding.mapping_provenance.source_sha256 !== review.source_sha256 || value.binding.mapping_provenance.spec_sha256 !== review.spec_sha256 || value.binding.mapping_provenance.normalized_sha256 !== review.normalized_sha256) throw new Error("提交回执身份不一致，请刷新目标包核对绑定。");
      setReview(null); setConfirmed(null); setStage(null); setMapping(null);
      setMessage({ key: contextKey, value: "已提交到独立目标包；原始文件与规范文件的身份均已保留。Study 尚未保存或运行。" });
      await onMapped(value as CsvMappingCommit);
    } catch (reason) { if (live(sequence, controller)) setMessage({ key: contextKey, value: reason instanceof Error ? reason.message : "提交失败，请重新校验。" }); }
    finally { finish(sequence, controller); }
  }

  return <section className="csv-mapping-editor" aria-labelledby={`${id}-title`} aria-busy={busy}>
    <h4 id={`${id}-title`}>将 CSV 列映射到标准列</h4>
    {!specification ? <p>{catalog ? "此角色没有受支持的列映射。请使用模板或下方标准文件上传。" : "正在核对当前包的映射目录…"}</p> : <>
      <p>含标题行的原始 CSV 先暂存。列选择、受支持单位转换和完整校验通过后，明确确认才更新目标包。{specification.single_value && "此角色只接受一个标准值。"}</p>
      {specification.unit_contract === "value.demand-mw-half-hour/v1" && <p>需求标准列为每 30 分钟平均功率 MW。源数据若为 MWh/period，请明确选择该单位：60 MWh ÷ 0.5 h = 120 MW；运行结果为 120 MW × 0.5 h = 60 MWh。下方预览显示转换后的 MW，不会推断或重采样时长。</p>}
      <label className="upload">{activity?.key === contextKey && activity.value === "upload" ? "正在暂存…" : "选择含标题行的 CSV"}<input type="file" accept=".csv,text/csv" disabled={locked} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file && !locked) void upload(file); }} /></label>
      {stage && <><p className="csv-mapping-identity">原文件 SHA <code>{stage.source_sha256}</code> · {stage.rows} 行 · {stage.source_bytes} bytes<br />目标 manifest SHA <code>{stage.target_manifest_sha256}</code></p>
        <div className="csv-mapping-columns">{columns.map((column, index) => <fieldset key={column.target} disabled={locked}><legend>{column.target}</legend><label><span>CSV 来源列</span><select value={column.source} onChange={(event) => changeColumn(index, { source: event.target.value })}><option value="">明确选择来源列</option>{stage.source_columns.map((name) => <option key={name} value={name}>{name}</option>)}</select></label>{column.target_unit === null ? <p>此列没有单位转换契约。</p> : <label><span>原始单位</span><select value={column.source_unit ?? ""} onChange={(event) => changeColumn(index, { source_unit: event.target.value || null })}>{[...new Set(specification.conversion_pairs.filter((pair) => pair.target_unit === column.target_unit).map((pair) => pair.source_unit))].map((unit) => <option key={unit} value={unit}>{unit}</option>)}</select></label>}<p>标准单位：{column.target_unit ?? "不适用"}。转换与时序假设由服务报告明确列出，不推测缺失列。</p></fieldset>)}</div>
        <button type="button" className="secondary" disabled={locked || columns.some((column) => !column.source)} onClick={() => void preview(Date.now())}>预览规范样例并校验完整文件</button></>}
      {review && <section className="csv-mapping-review" aria-label="映射审阅报告"><h5>{review.valid ? "完整校验通过，等待明确提交" : "校验未通过，请修改文件或映射"}</h5><p>原文件 SHA <code>{review.source_sha256}</code><br />规范文件 SHA <code>{review.normalized_sha256 ?? "尚不可用"}</code><br />映射 SHA <code>{review.spec_sha256}</code></p>{review.errors.length > 0 && <ul>{review.errors.map((error, index) => <li key={index}>{error}</li>)}</ul>}{review.warnings.length > 0 && <ul>{review.warnings.map((warning, index) => <li key={index}>{warning}</li>)}</ul>}<details open><summary>规范化样例、单位与映射</summary><pre>{JSON.stringify({ columns: review.columns, rows: review.rows, sample_rows: review.sample_rows }, null, 2)}</pre></details><details open><summary>完整文件校验报告</summary><pre>{JSON.stringify(review.validation, null, 2)}</pre></details><p>审阅有效期至 {review.expires_at}。修改角色、文件、映射或目标包版本后必须重新校验。</p>{review.valid && <><label className="csv-mapping-confirm"><input type="checkbox" disabled={locked} checked={confirmed === review.review_id} onChange={(event) => setConfirmed(event.target.checked ? review.review_id : null)} /><span>我已核对列、单位、样例和报告，确认只更新此独立目标包的角色绑定。</span></label><button type="button" className="primary" disabled={locked || confirmed !== review.review_id} onClick={() => void commit(Date.now())}>确认提交映射后的文件</button></>}</section>}
    </>}{readOnlyReason && <p role="status">{readOnlyReason}</p>}{message && <p role="status">{message}</p>}
  </section>;
}
