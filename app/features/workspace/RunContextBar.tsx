"use client";

import { resolveRunContext, type ContextRun, type FrozenRunContext } from "./runContext";
import "./run-context.css";

export default function RunContextBar({ run, frozen }: {
  run?: ContextRun | null;
  frozen?: FrozenRunContext | null;
}) {
  const context = resolveRunContext({ run, frozen });
  const label = (value: string) => value.replaceAll("_", " ");
  const identityAvailable = context.kind === "ready" || context.kind === "partial";
  return <section className={`run-context-bar run-context-${context.kind}`} aria-label="Selected Run context" aria-busy={context.kind === "loading"}>
    <div className="run-context-heading">
      <div><span className="run-context-eyebrow">Selected Run · read-only source</span>
        <strong>{context.studyName ?? context.studyId ?? "No Run selected"}</strong>
        {context.runId && <code>{context.runId}</code>}
      </div>
      {context.runId && <div className="run-context-statuses">
        <span><small>Execution</small><b>{label(context.executionStatus)}</b></span>
        <span><small>Contract check</small><b>{label(context.contractStatus)}</b></span>
        <span><small>Scientific validation</small><b>{label(context.scientificStatus)}</b></span>
      </div>}
    </div>
    {context.issue && <p className="run-context-notice" role="status">{context.issue}</p>}
    {context.runId && <p className="run-context-scope"><b>Run scope</b> {context.scope.label}
      {context.scope.configuredPeriods !== undefined && <> · {context.scope.configuredPeriods.toLocaleString("en-GB")} periods configured</>}
      {context.scope.years && <> · {context.scope.years.join(", ")}</>}
      <small>Scope describes the Run configuration, not a claim of complete scientific evidence.</small>
    </p>}
    {identityAvailable && <>
      <div className="run-context-sources">
        <span><small>Frozen Study revision</small><b>{context.revisionNumber === undefined ? "Not recorded" : context.revisionNumber}</b></span>
        <span><small>Frozen data pack</small><code>{context.dataPackId ?? "Not recorded"}</code></span>
        <span><small>Frozen network overlay</small><code>{context.networkPackId ?? "Not recorded"}</code></span>
      </div>
      <details className="run-context-details"><summary>Source identity details</summary>
        <dl>{[
          ["Study ID", context.studyId],
          ["Study revision SHA-256", context.revisionSha],
          ["Data pack manifest SHA-256", context.dataPackSha],
          ["Network manifest SHA-256", context.networkPackSha],
          ["Input snapshot ID", context.snapshotId],
          ["Input tree SHA-256", context.inputTreeSha],
        ].map(([name, value]) => <div key={name}><dt>{name}</dt><dd><code>{value ?? "Not recorded"}</code></dd></div>)}</dl>
        <p>These are the identities saved for this Run. Loading them does not establish scientific validation.</p>
      </details>
    </>}
    {context.sourceStudyStatus === "trash" && <p className="run-context-notice">The source Study is in trash. Historical Run evidence remains readable.</p>}
    {context.sourceStudyStatus === "missing" && <p className="run-context-notice">The source Study is missing. Available frozen Run evidence remains readable.</p>}
  </section>;
}
