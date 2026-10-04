"use client";

type BaselineRun = { id:string; project_id:string; mode:string; status:string; recorded_project_revision_sha256?:string|null };
export default function BaselineRuns({ sourceStudyId, sourceRevision, runs, onSelect }: {
  sourceStudyId:string; sourceRevision:string; runs:BaselineRun[]; onSelect:(run:BaselineRun)=>void;
}) {
  const sourceRuns = runs.filter((run) => run.project_id === sourceStudyId);
  const matches = sourceRuns.filter((run) => run.recorded_project_revision_sha256 === sourceRevision);
  const unknown = sourceRuns.filter((run) => !run.recorded_project_revision_sha256).length;
  const changed = sourceRuns.length - matches.length - unknown;
  return <details className="baseline-runs"><summary>此来源修订的 Runs · {matches.length}</summary>
    <p>按 Run 保存的 Study 修订匹配。选择运行后仍需核对数据、方法和执行范围，不能仅凭名称认定为对照。</p>
    {matches.length ? <div className="journey-origin-actions">{matches.map((run) => <button className="secondary" key={run.id} onClick={() => onSelect(run)}><code>{run.id}</code><small>{run.mode} · {run.status}</small></button>)}</div> : <p>尚无可确认属于此修订的 Run。可以明确启动基线运行，或查看其他修订的历史结果。</p>}
    {(unknown > 0 || changed > 0) && <small>{changed} 个 Run 属于其他修订；{unknown} 个缺少修订记录，未自动选作基线。</small>}
  </details>;
}
