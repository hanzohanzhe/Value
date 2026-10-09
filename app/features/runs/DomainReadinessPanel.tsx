import type { View } from "../shared/navigation";
import type { DomainReadiness, DomainSection } from "./types";
import { Badge, formatNumber } from "../shared/presentation";

import { PUBLIC_CAPABILITY_DOMAINS, domainLabel } from "../shared/domainConstants";
import { useT } from "../../i18n/LocaleProvider";

// M2-N3 (round R1-5): ready physical inputs do not read as "ready to run" while
// readiness has errors (the title is the message "domainReadiness.blockedTitle").

export default function DomainReadinessPanel({ readiness, onNavigate, runBlocked = false }: { readiness: DomainReadiness; onNavigate: (view: View) => void; runBlocked?: boolean }) {
  const t = useT();
  const blockedPreview = readiness.ready && runBlocked;
  const target = (control?: string): View => control === "data" ? "data" : control === "modules" || control === "extensions" ? "models" : "projects";
  return <section className="domain-readiness" aria-label={t("domainReadiness.label")}>
    <header><div><span>{t("domainReadiness.kicker")}</span><h3>{t("domainReadiness.title")}</h3><p>{readiness.bounded ? t("domainReadiness.inspectedBounded", { count: readiness.preview_periods, requested: readiness.requested_periods }) : t("domainReadiness.inspected", { count: readiness.preview_periods })}</p></div>{blockedPreview ? <span className="domain-readiness-blocked" title={t("domainReadiness.blockedTitle")}><Badge tone="warn">{t("domainReadiness.blocked")}</Badge></span> : <Badge tone={readiness.ready ? "good" : "warn"}>{readiness.status.replaceAll("_", " ")}</Badge>}</header>
    <div className="domain-readiness-grid">{PUBLIC_CAPABILITY_DOMAINS.map((id) => [id, readiness.sections[id]] as const).filter((entry): entry is readonly [string, DomainSection] => Boolean(entry[1])).map(([id, section]) => <article key={id}><div><span>{domainLabel(id)}</span><Badge tone={section.status === "ready" ? "good" : section.status === "blocked" ? "warn" : "blue"}>{section.status}</Badge></div><p>{section.claim ?? section.error ?? t("domainReadiness.summary")}</p><dl>{Object.entries(section.metrics ?? {}).slice(0, 6).map(([name, metric]) => <div key={name}><dt>{name.replaceAll("_", " ")}</dt><dd>{typeof metric.value === "number" ? formatNumber(metric.value, Number.isInteger(metric.value) ? 0 : 3) : String(metric.value ?? metric.status)} <small>{metric.unit}</small></dd></div>)}</dl>{id === "hydrology" && <small className="truth-note">{t("domainReadiness.pumpedHydro")}</small>}</article>)}</div>
    {readiness.issues.length > 0 && <div className="domain-issues">{readiness.issues.map((issue) => <article key={`${issue.code}-${issue.message}`} className={issue.severity}><div><code>{issue.code}</code><b>{issue.message}</b><small>{issue.corrective_action}</small></div><button className="text-button" onClick={() => onNavigate(target(issue.control))}>{issue.control ? t("domainReadiness.open", { control: issue.control }) : t("domainReadiness.openStudy")}</button></article>)}</div>}
  </section>;
}

