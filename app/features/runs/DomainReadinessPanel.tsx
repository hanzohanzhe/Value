import type { View } from "../shared/navigation";
import type { DomainReadiness, DomainSection } from "./types";
import { Badge, formatNumber } from "../shared/presentation";

import { PUBLIC_CAPABILITY_DOMAINS } from "../shared/domainConstants";

export default function DomainReadinessPanel({ readiness, onNavigate }: { readiness: DomainReadiness; onNavigate: (view: View) => void }) {
  const target = (control?: string): View => control === "data" ? "data" : control === "modules" || control === "extensions" ? "models" : "projects";
  return <section className="domain-readiness" aria-label="Physical system readiness">
    <header><div><span>Physical system preview</span><h3>What this Study will actually run</h3><p>{readiness.preview_periods} canonical periods inspected{readiness.bounded ? ` from ${readiness.requested_periods} requested periods` : ""}. This is input review, not a solver result.</p></div><Badge tone={readiness.ready ? "good" : "warn"}>{readiness.status.replaceAll("_", " ")}</Badge></header>
    <div className="domain-readiness-grid">{PUBLIC_CAPABILITY_DOMAINS.map((id) => [id, readiness.sections[id]] as const).filter((entry): entry is readonly [string, DomainSection] => Boolean(entry[1])).map(([id, section]) => <article key={id}><div><span>{id.replaceAll("_", " ")}</span><Badge tone={section.status === "ready" ? "good" : section.status === "blocked" ? "warn" : "blue"}>{section.status}</Badge></div><p>{section.claim ?? section.error ?? "Canonical input summary"}</p><dl>{Object.entries(section.metrics ?? {}).slice(0, 6).map(([name, metric]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{typeof metric.value === "number" ? formatNumber(metric.value, Number.isInteger(metric.value) ? 0 : 3) : String(metric.value ?? metric.status)} <small>{metric.unit}</small></dd></div>)}</dl>{id === "hydrology" && <small className="truth-note">Pumped hydro remains in electrical storage.</small>}</article>)}</div>
    {readiness.issues.length > 0 && <div className="domain-issues">{readiness.issues.map((issue) => <article key={`${issue.code}-${issue.message}`} className={issue.severity}><div><code>{issue.code}</code><b>{issue.message}</b><small>{issue.corrective_action}</small></div><button className="text-button" onClick={() => onNavigate(target(issue.control))}>Open {issue.control ?? "Study"}</button></article>)}</div>}
  </section>;
}

