"use client";

import { useT } from "../../i18n/LocaleProvider";

type BaselineRun = { id:string; project_id:string; mode:string; status:string; recorded_project_revision_sha256?:string|null };
export default function BaselineRuns({ sourceStudyId, sourceRevision, runs, onSelect }: {
  sourceStudyId:string; sourceRevision:string; runs:BaselineRun[]; onSelect:(run:BaselineRun)=>void;
}) {
  const t = useT();
  const sourceRuns = runs.filter((run) => run.project_id === sourceStudyId);
  const matches = sourceRuns.filter((run) => run.recorded_project_revision_sha256 === sourceRevision);
  const unknown = sourceRuns.filter((run) => !run.recorded_project_revision_sha256).length;
  const changed = sourceRuns.length - matches.length - unknown;
  return <details className="baseline-runs"><summary>{t("baseline.summary", { count: matches.length })}</summary>
    <p>{t("baseline.intro")}</p>
    {matches.length ? <div className="journey-origin-actions">{matches.map((run) => <button className="secondary" key={run.id} onClick={() => onSelect(run)}><code>{run.id}</code><small>{run.mode} · {run.status}</small></button>)}</div> : <p>{t("baseline.none")}</p>}
    {(unknown > 0 || changed > 0) && <small>{t("baseline.others", { changed, unknown })}</small>}
  </details>;
}
