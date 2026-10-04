"use client";

import { useCallback, useId, useState } from "react";
import "./journey-data-editor.css";
import CsvMappingEditor from "../data/CsvMappingEditor";
import type { CsvMappingCommit } from "../data/csvMappingTypes";

export type JourneyBinding = { filename: string; sha256: string; validation?: { status?: string }; mapping_provenance?: { source_sha256: string; spec_sha256: string; normalized_sha256: string } };
export type JourneyDataSlot = { role: string; label: string; required: boolean; formats: string[]; supported_formats?: string[]; unit?: string; time_semantics?: string; template_available?: boolean };
export type JourneyDataEditorProps = {
  sourceName: string;
  sourcePackName: string;
  targetPack?: { id: string; name: string; bindings: Record<string, JourneyBinding>; manifest_sha256?: string };
  sourceBindings: Record<string, JourneyBinding>;
  slots: JourneyDataSlot[];
  apiOrigin: string;
  networkPackId?: string;
  readOnlyReason?: string;
  busy: boolean;
  onUpload: (role: string, file: File) => Promise<void> | void;
  onPreview: (role: string) => Promise<void> | void;
  onReturn: () => void;
  onMapped?: (result: CsvMappingCommit) => Promise<void> | void;
};

export default function JourneyDataEditor({ sourceName, sourcePackName, targetPack, sourceBindings, slots, apiOrigin, networkPackId, readOnlyReason, busy, onUpload, onPreview, onReturn, onMapped }: JourneyDataEditorProps) {
  const id = useId();
  const [selectedRole, setSelectedRole] = useState("");
  const slot = slots.find((item) => item.role === selectedRole) ?? slots[0];
  const mappingContext = JSON.stringify([apiOrigin, targetPack?.id, targetPack?.manifest_sha256, slot?.role, busy, readOnlyReason]);
  const [mappingActivity, setMappingActivity] = useState<{ key: string; busy: boolean } | null>(null);
  const onMappingBusy = useCallback((mappingBusy: boolean) => setMappingActivity({ key: mappingContext, busy: mappingBusy }), [mappingContext]);
  const effectiveBusy = busy || (mappingActivity?.key === mappingContext && mappingActivity.busy);
  const original = slot ? sourceBindings[slot.role] : undefined;
  const binding = slot ? targetPack?.bindings[slot.role] : undefined;
  const formats = slot?.supported_formats?.length ? slot.supported_formats : slot?.formats ?? [];
  const added = slots.filter((item) => targetPack?.bindings[item.role] && !sourceBindings[item.role]).length;
  const changed = slots.filter((item) => targetPack?.bindings[item.role] && sourceBindings[item.role] && targetPack.bindings[item.role].sha256 !== sourceBindings[item.role].sha256).length;
  const missing = slots.filter((item) => item.required && !targetPack?.bindings[item.role]).length;
  const disabled = effectiveBusy || Boolean(readOnlyReason) || !targetPack || !slot;
  return <section className="journey-data-editor panel" aria-labelledby={`${id}-title`} aria-busy={effectiveBusy}>
    <header><span>add your new data</span><h3 id={`${id}-title`}>将我的文件连接到独立 BASE 包</h3><p>基线 Study：{sourceName || "不可用"} · 原 BASE 包：{sourcePackName || "不可用"}</p></header>
    <p>目标包：<b>{targetPack?.name ?? "尚未选择"}</b>{targetPack && <code>{targetPack.id}</code>}</p>
    <p className="journey-data-network">网络覆盖包：<code>{networkPackId || "未配置"}</code>。沿用原 Study 设置；网络覆盖包由 Data Workbench 管理。</p>
    {!targetPack && <p role="status">先返回研究引导，复制基线 BASE 包或选择其他已安装的 BASE 包。</p>}
    {readOnlyReason && <p role="status">{readOnlyReason}</p>}
    {targetPack && <p className="journey-data-count">新增 {added} · SHA 改变 {changed} · 必需角色缺失 {missing}{added + changed === 0 && "。目前沿用原文件，还没有检测到数据变化。"}</p>}
    <label className="journey-data-role" htmlFor={`${id}-role`}><span>1. 选择文件的语义角色</span><select id={`${id}-role`} value={slot?.role ?? ""} disabled={effectiveBusy || Boolean(readOnlyReason) || !slots.length} onChange={(event) => setSelectedRole(event.target.value)}>{slots.map((item) => <option key={item.role} value={item.role}>{item.label} · {item.role}{item.required ? " · 必需" : ""}</option>)}</select></label>
    {slot && <><p><code>{slot.role}</code> · {slot.required ? "必需" : "可选"} · 标准格式 {formats.join(" / ") || "未声明"}{slot.unit && ` · ${slot.unit}`}{slot.time_semantics && ` · ${slot.time_semantics}`}</p>
      <div className="journey-data-files"><div><b>原文件</b><span>{original?.filename ?? "没有绑定"}</span>{original && <code>SHA {original.sha256}</code>}</div><div><b>目标文件</b><span>{binding?.filename ?? "没有绑定"}</span>{binding && <><code>SHA {binding.sha256}</code><span>校验：{binding.validation?.status ?? "尚未记录"}</span>{binding.mapping_provenance && <><span>映射保留的原始文件</span><code>SHA {binding.mapping_provenance.source_sha256}</code><span>规范文件</span><code>SHA {binding.mapping_provenance.normalized_sha256}</code><span>映射规则</span><code>SHA {binding.mapping_provenance.spec_sha256}</code></>}</>}</div></div>
      <p>2. 使用角色模板或符合契约的标准格式文件。标准文件可直接校验上传；受支持的 CSV 角色也可先映射列和单位，审阅完整报告后再确认提交。</p>
      {targetPack?.manifest_sha256 && onMapped ? <CsvMappingEditor key={mappingContext} apiOrigin={apiOrigin} packId={targetPack.id} manifestSha256={targetPack.manifest_sha256} role={slot.role} disabled={busy} readOnlyReason={readOnlyReason} onMapped={onMapped} onBusyChange={onMappingBusy} /> : <p>CSV 列映射需要当前目标包版本；请刷新目标包，或使用标准文件上传。</p>}
      <div className="journey-data-actions">{slot.template_available && <a className="secondary" href={`${apiOrigin}/api/data-contracts/${encodeURIComponent(slot.role)}/template`}>下载模板</a>}{binding && <button type="button" className="secondary" disabled={effectiveBusy} onClick={() => void onPreview(slot.role)}>预览目标文件</button>}<label className="upload">{effectiveBusy ? "正在处理…" : "选择并校验我的文件"}<input type="file" accept={formats.map((format) => `.${format}`).join(",")} disabled={disabled} onChange={(event) => { const file = event.target.files?.[0]; event.target.value = ""; if (file && !disabled) void onUpload(slot.role, file); }} /></label></div>
    </>}
    <p>文件校验和 Study 运行前检查是不同步骤。保存新 Study 后，在 Runs 明确选择 scope 并执行 Check readiness。</p>
    <button type="button" className="secondary" onClick={onReturn} disabled={effectiveBusy}>保留目标包并返回研究引导</button>
  </section>;
}
