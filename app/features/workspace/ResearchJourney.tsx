"use client";

import { useId, useRef, useState, type FormEvent } from "react";
import "./research-journey.css";

export type JourneyStudy = {
  id: string;
  name: string;
  revision_sha256?: string;
  revision_number?: number;
  data_pack_id: string;
  start_year: number;
  end_year: number;
  modules: Record<string, string>;
};

export type JourneyPack = {
  id: string;
  name: string;
  complete: boolean;
  valid_required_count: number;
  required_count: number;
  manifest_sha256?: string;
  data_pack_type?: string;
  bindings?: Record<string, { filename: string; sha256: string }>;
};

export type ResearchJourneyProps = {
  intent: "reproduce" | "data";
  studies: JourneyStudy[];
  packs: JourneyPack[];
  initialStudyId: string;
  apiOrigin: string;
  online: boolean;
  onCreated: (studyId: string) => Promise<void> | void;
  targetPackId: string;
  onTargetPackChange: (id: string) => void;
  onPackCreated: () => Promise<void>;
  onOpenData: (context: { sourceStudyId: string; sourceRevisionSha256: string; targetPackId: string }) => void;
  onOpenLearn: () => void;
  onOpenRuns: (studyId: string) => void;
  onReviewSource: (studyId: string) => void;
};

type DeriveResponse = { project?: { id?: string }; error?: string; detail?: string };

export default function ResearchJourney({
  intent, studies, packs, initialStudyId, apiOrigin, online,
  onCreated, onOpenData, onOpenLearn, onOpenRuns, onReviewSource, targetPackId, onTargetPackChange, onPackCreated,
}: ResearchJourneyProps) {
  const fieldId = useId();
  // An explicit selection, including one that later disappears, stays selected.
  const [sourceId, setSourceId] = useState(() => initialStudyId || studies[0]?.id || "");
  const [newName, setNewName] = useState("");
  const [packName, setPackName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submissionLock = useRef(false);
  const selectedSourceId = sourceId || initialStudyId || studies[0]?.id || "";
  const source = studies.find((study) => study.id === selectedSourceId);
  const originalPack = packs.find((pack) => pack.id === source?.data_pack_id);
  const targetPack = packs.find((pack) => pack.id === targetPackId);
  const changingData = intent === "data";
  const availablePacks = packs.filter((pack) => pack.id !== source?.data_pack_id && pack.data_pack_type !== "network_overlay");
  const targetUnavailable = Boolean(targetPackId && !availablePacks.some((pack) => pack.id === targetPackId));
  const hasRevision = Boolean(source?.revision_sha256?.trim());
  const dataSelected = !changingData || Boolean(targetPack && !targetUnavailable && targetPack.id !== source?.data_pack_id);
  const canCreate = Boolean(online && source && hasRevision && dataSelected && newName.trim() && !busy);
  const createLabel = changingData ? "创建换数据 Study" : "创建复现 Study";
  const reviewStep = changingData ? 3 : 2;

  function openData(packId = targetPackId) {
    if (!source) return;
    onOpenData({ sourceStudyId: source.id, sourceRevisionSha256: source.revision_sha256 ?? "", targetPackId: packId });
  }

  async function clonePack() {
    if (!source || !originalPack?.manifest_sha256 || originalPack.data_pack_type === "network_overlay" || !online || !packName.trim() || submissionLock.current) return;
    submissionLock.current = true; setBusy(true); setError("");
    let createdPackId = "";
    try {
      const response = await fetch(`${apiOrigin}/api/data-packs/${encodeURIComponent(originalPack.id)}/clone`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ schema_version: "value.data-pack-clone-request/v1", name: packName.trim(), source_manifest_sha256: originalPack.manifest_sha256 }),
      });
      const payload = await response.json() as { data_pack?: { id?: string }; error?: string; detail?: string };
      if (response.status !== 201) throw new Error(payload.error || payload.detail || "复制失败，请检查基线数据包后重试。");
      if (!payload.data_pack?.id || typeof payload.data_pack.id !== "string" || payload.data_pack.id === originalPack.id) throw new Error("复制结果缺少独立数据包身份，请刷新后确认。");
      createdPackId = payload.data_pack.id;
      onTargetPackChange(createdPackId);
      await onPackCreated();
      openData(payload.data_pack.id);
    } catch (cause) { setError(createdPackId ? `独立数据包 ${createdPackId} 已创建，但列表未刷新。请重新加载工作区后选择该包；无需再次复制。` : cause instanceof Error ? cause.message : "数据包复制失败。"); }
    finally { submissionLock.current = false; setBusy(false); }
  }

  async function createStudy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canCreate || !source || submissionLock.current) return;
    submissionLock.current = true;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${apiOrigin}/api/projects/${encodeURIComponent(source.id)}/derive`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          intent,
          name: newName.trim(),
          source_revision_sha256: source.revision_sha256,
          data_pack_id: changingData ? targetPackId : source.data_pack_id,
        }),
      });
      let payload: DeriveResponse;
      try {
        payload = await response.json() as DeriveResponse;
      } catch {
        throw new Error("服务没有返回可识别的创建结果，请稍后重试。");
      }
      if (!response.ok) {
        throw new Error(typeof payload.error === "string" ? payload.error
          : typeof payload.detail === "string" ? payload.detail : "创建失败，请检查基线版本和数据包后重试。");
      }
      if (typeof payload.project?.id !== "string" || !payload.project.id) {
        throw new Error("创建结果缺少 Study 信息，请刷新研究列表后确认。");
      }
      await onCreated(payload.project.id);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "暂时无法创建 Study，请稍后重试。");
    } finally {
      submissionLock.current = false;
      setBusy(false);
    }
  }

  return (
    <section className="research-journey" aria-labelledby={`${fieldId}-title`}>
      <header className="research-journey-heading">
        <span>研究路径</span>
        <h2 id={`${fieldId}-title`} lang="en">{changingData ? "add your new data" : "reproduce from existing data"}</h2>
        <p>{changingData ? "沿用一项研究的方法，换用自己的数据，创建一项可对照的新研究。" : "从已有研究的当前保存版本创建新 Study，再运行并对照结果。"}</p>
      </header>

      <form onSubmit={createStudy} aria-busy={busy}>
        <ol className="research-journey-steps">
          <li className="research-journey-step">
            <header><span aria-hidden="true">1</span><h3>选择基线 Study</h3></header>
            {studies.length === 0 ? (
              <div className="research-journey-empty">
                <p>还没有可用的 Study。先从 VALUE 101 教学示例创建一项基线研究，再回到这里。</p>
                <button type="button" onClick={onOpenLearn} disabled={busy}>打开 VALUE 101</button>
              </div>
            ) : (
              <label className="research-journey-field" htmlFor={`${fieldId}-source`}>
                <span>已有研究</span>
                <select id={`${fieldId}-source`} value={selectedSourceId} disabled={busy}
                  onChange={(event) => { setSourceId(event.target.value); setError(""); }}>
                  {selectedSourceId && !source && <option value={selectedSourceId}>所选 Study 已不可用，请重新选择</option>}
                  {studies.map((study) => <option key={study.id} value={study.id}>{study.name}</option>)}
                </select>
              </label>
            )}
            {selectedSourceId && !source && <p className="research-journey-warning" role="status">之前选择的基线已不可用。请明确选择另一项 Study 后继续。</p>}
            <p className="research-journey-hint">这里使用 Study 的当前保存版本。历史 Run 保存的版本和输入可能不同，可先查看基线 Runs 确认比较对象。</p>
            {source && <div className="research-journey-baseline-actions">
              <button type="button" onClick={() => onOpenRuns(source.id)} disabled={busy}>查看基线 Runs</button>
              <button type="button" onClick={() => onReviewSource(source.id)} disabled={busy}>检查 / 更新基线</button>
            </div>}
          </li>

          {changingData && <li className="research-journey-step">
            <header><span aria-hidden="true">2</span><h3>准备独立 BASE 数据包</h3></header>
            <label className="research-journey-field" htmlFor={`${fieldId}-pack-name`}><span>独立数据包名称</span><input id={`${fieldId}-pack-name`} value={packName} disabled={busy || !source} placeholder="例如：我的需求数据包" onChange={(event) => setPackName(event.target.value)} /></label>
            <button type="button" onClick={() => void clonePack()} disabled={busy || !online || !source || !originalPack?.manifest_sha256 || originalPack.data_pack_type === "network_overlay" || !packName.trim()}>复制基线 BASE 包并加入我的文件</button>
            <p className="research-journey-hint">复制保留原始输入，并生成独立数据包。进入 Data 后，选择文件的语义角色并替换；只复制原文件还没有改变数据。网络覆盖包沿用基线配置，由 Data Workbench 管理。</p>
            {originalPack?.data_pack_type === "network_overlay" && <p className="research-journey-warning">当前基线引用的是网络覆盖产品，不能作为 BASE 包复制。请选择使用基础数据包的基线；网络覆盖包请在 Data Workbench 管理。</p>}
            {source && !originalPack?.manifest_sha256 && <p className="research-journey-warning">基线包缺少 manifest 身份，暂不能复制；请先检查数据包。</p>}
            <label className="research-journey-field" htmlFor={`${fieldId}-pack`}>
              <span>已安装的数据包</span>
              <select id={`${fieldId}-pack`} value={targetPackId} disabled={busy || !source}
                onChange={(event) => { onTargetPackChange(event.target.value); setError(""); }}>
                <option value="">选择与基线不同的数据包</option>
                {targetUnavailable && <option value={targetPackId}>所选数据包已不可用或与基线相同，请重新选择</option>}
                {availablePacks.map((pack) => <option key={pack.id} value={pack.id}>{pack.name}</option>)}
              </select>
            </label>
            {targetUnavailable && <p className="research-journey-warning" role="status">请选择仍已安装、且与基线不同的数据包。</p>}
            {source && availablePacks.length === 0 && <p className="research-journey-hint">目前没有其他已安装的数据包。可先进入 Data 安装并校验自己的数据。</p>}
            {targetPack && !targetUnavailable && <p className="research-journey-pack-status">数据包文件状态：{targetPack.complete ? "完整" : "待补齐"} · 必需项有效 {targetPack.valid_required_count} / {targetPack.required_count}</p>}
            <p className="research-journey-hint">文件完整度不代表研究预检通过。创建时服务会检查数据与研究的兼容性，运行前仍需 Check readiness。</p>
            <button type="button" onClick={() => openData()} disabled={busy || !source}>进入 Data 安装 / 校验</button>
          </li>}

          <li className="research-journey-step">
            <header><span aria-hidden="true">{reviewStep}</span><h3>核对新研究</h3></header>
            <label className="research-journey-field" htmlFor={`${fieldId}-name`}>
              <span>新 Study 名称</span>
              <input id={`${fieldId}-name`} value={newName} required disabled={busy} autoComplete="off"
                placeholder={changingData ? "例如：新数据对照研究" : "例如：基线复现研究"}
                onChange={(event) => { setNewName(event.target.value); setError(""); }} />
            </label>
            {source ? <>
              <dl className="research-journey-review">
                <div><dt>基线</dt><dd>{source.name}</dd></div>
                <div><dt>年份</dt><dd>{source.start_year} – {source.end_year}</dd></div>
                <div><dt>基线保存版本</dt><dd>{source.revision_number !== undefined ? `Revision ${source.revision_number}` : "版本编号未记录"}
                  {hasRevision ? <code title={source.revision_sha256}>{source.revision_sha256}</code> : <span className="research-journey-warning">缺少版本标识，暂不能创建</span>}</dd></div>
                <div><dt>原数据包</dt><dd>{originalPack?.name ?? source.data_pack_id}<code>{source.data_pack_id}</code></dd></div>
                <div><dt>{changingData ? "新数据包" : "新研究数据包"}</dt><dd>{changingData ? targetPack?.name ?? "尚未选择" : originalPack?.name ?? source.data_pack_id}
                  {changingData && targetPack && <code>{targetPack.id}</code>}</dd></div>
              </dl>
              <details className="research-journey-modules">
                <summary>查看沿用的模块</summary>
                <div className="research-journey-table-scroll" role="region" aria-label="沿用的模块" tabIndex={0}>
                <table>
                  <caption>沿用的模块设置</caption>
                  <thead><tr><th scope="col">模块角色</th><th scope="col">已选模块</th></tr></thead>
                  <tbody>{Object.entries(source.modules).map(([role, moduleId]) => <tr key={role}><th scope="row">{role}</th><td>{moduleId}</td></tr>)}</tbody>
                </table>
                {Object.keys(source.modules).length === 0 && <p className="research-journey-hint">基线尚未记录模块设置，创建时由服务检查。</p>}
                </div>
              </details>
            </> : <p className="research-journey-hint">选择可用的基线 Study 后，这里会显示年份、保存版本、模块与数据包。</p>}
          </li>

          <li className="research-journey-step research-journey-create">
            <header><span aria-hidden="true">{reviewStep + 1}</span><h3>创建后，在 Runs 启动</h3></header>
            <p>创建只保存新的 Study。接着在 Runs 选择 scope，执行 Check readiness，再明确启动 Run。完成后，对照基线结果。</p>
            {!online && <p className="research-journey-warning" role="status">本地服务当前未连接。连接恢复后才能创建，当前选择会保留。</p>}
            {error && <>
              <p className="research-journey-error" role="alert">{error}</p>
              <p className="research-journey-hint">若基线版本、数据或模块已改变，请检查基线并保存新版本后重试。</p>
            </>}
            <button className="research-journey-primary" type="submit" disabled={!canCreate}>{busy ? "正在创建 Study…" : createLabel}</button>
          </li>
        </ol>
      </form>
    </section>
  );
}
