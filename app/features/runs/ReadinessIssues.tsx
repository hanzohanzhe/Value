"use client";

import { useState } from "react";
import { StatusPill } from "../shared/Callout";
import { readinessGroups, rowTitle, type ReadinessGroup, type ReadinessIssue } from "./readinessGroups.ts";
import "./readiness-issues.css";

/** Spec 11.1 (S-D1): every readiness issue, grouped by priority; nothing is truncated. */
export default function ReadinessIssues({ errors, warnings }: { errors?: readonly ReadinessIssue[] | null; warnings?: readonly ReadinessIssue[] | null }) {
  const groups = readinessGroups({ errors, warnings });
  if (!groups.length) return null;
  return <div className="readiness-groups">{groups.map((group) => <ReadinessGroupView key={group.id} group={group} />)}</div>;
}

function ReadinessGroupView({ group }: { group: ReadinessGroup }) {
  const [open, setOpen] = useState(group.defaultOpen);
  const expanded = !group.collapsible || open;
  const listId = `readiness-group-${group.id}`;
  return <section className={`readiness-group value-new-control ${group.id}`} aria-label={`${group.label}: ${group.count}`}>
    <header>
      <StatusPill tone={group.tone}>{group.label} · {group.count}</StatusPill>
      {group.collapsible && <button type="button" className="readiness-toggle" aria-expanded={expanded} aria-controls={listId} onClick={() => setOpen(!open)}>{expanded ? "Hide" : `Show ${group.count}`}</button>}
    </header>
    {expanded && <ul id={listId}>{group.rows.map((row) => <li key={row.key} title={rowTitle(row)}>
      <span className="readiness-row-text"><b>{row.text}</b>{row.count > 1 && <span className="readiness-count" aria-label={`${row.count} occurrences`}> ×{row.count}</span>}</span>
      {row.objects.length > 0 && <small className="readiness-objects">{row.objects.length === 1 ? row.objects[0] : `${row.objects[0]} and ${row.objects.length - 1} more`}</small>}
      {row.correctiveAction && <small>{row.correctiveAction}</small>}
      <code>{row.code}</code>
    </li>)}</ul>}
  </section>;
}
