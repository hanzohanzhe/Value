"use client";

import { useState } from "react";
import { Callout, StatusPill } from "../shared/Callout";
import { MODULE_SOURCE_CHANGED, readinessGroups, rowTitle, sourceChangeWarnings, type ReadinessGroup, type ReadinessIssue } from "./readinessGroups.ts";
import "./readiness-issues.css";

/** Spec 11.1 (S-D1): every readiness issue, grouped by priority; nothing is truncated. */
export default function ReadinessIssues({ errors, warnings }: { errors?: readonly ReadinessIssue[] | null; warnings?: readonly ReadinessIssue[] | null }) {
  // R3M-5 (round R2): a module source change is shown once, in its Callout, not again in a group.
  const sourceChanges = sourceChangeWarnings(warnings);
  const groups = readinessGroups({ errors, warnings }, sourceChanges.length ? new Set([MODULE_SOURCE_CHANGED]) : undefined);
  if (!groups.length && !sourceChanges.length) return null;
  return <div className="readiness-groups">
    {sourceChanges.length > 0 && <Callout tone="caution" className="readiness-source-changed" title={sourceChanges.length === 1 ? "Module source changed since install" : `${sourceChanges.length} module sources changed since install`}>
      {sourceChanges.map((issue) => <p key={issue.message}>{issue.message}</p>)}
    </Callout>}
    {groups.map((group) => <ReadinessGroupView key={group.id} group={group} />)}
  </div>;
}

function ReadinessGroupView({ group }: { group: ReadinessGroup }) {
  const [open, setOpen] = useState(group.defaultOpen);
  const expanded = !group.collapsible || open;
  const listId = `readiness-group-${group.id}`;
  // div, not section/header/b: the older `.preflight-card section …` rules must not restyle these rows.
  return <div role="group" className={`readiness-group value-new-control ${group.id}`} aria-label={`${group.label}: ${group.count}`}>
    <div className="readiness-group-head">
      <StatusPill tone={group.tone}>{group.label} · {group.count}</StatusPill>
      {group.collapsible && <button type="button" className="readiness-toggle" aria-expanded={expanded} aria-controls={listId} onClick={() => setOpen(!open)}>{expanded ? "Hide" : `Show ${group.count}`}</button>}
    </div>
    {expanded && <ul id={listId}>{group.rows.map((row) => <li key={row.key} title={rowTitle(row)}>
      <span className="readiness-row-text"><span className="readiness-row-title">{row.text}</span>{row.count > 1 && <span className="readiness-count" aria-label={`${row.count} occurrences`}> ×{row.count}</span>}</span>
      {row.objects.length > 0 && <small className="readiness-objects">{row.objects.length === 1 ? row.objects[0] : `${row.objects[0]} and ${row.objects.length - 1} more`}</small>}
      {row.correctiveAction && <small>{row.correctiveAction}</small>}
      <code>{row.code}</code>
    </li>)}</ul>}
  </div>;
}
