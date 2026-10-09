import type { Project } from "../studies/types";
import type { ResourceReadiness, FrozenInputSnapshot } from "../runs/types";
import { Badge, formatBytes, formatNumber } from "../shared/presentation";
import { frozenManifestLabel, frozenManifestNote } from "../workspace/runContext";
import { useT } from "../../i18n/LocaleProvider";

export default function ReadinessEvidence({
  readiness,
  project,
  snapshot,
  frozen = false,
}: {
  readiness: ResourceReadiness;
  project?: Project;
  snapshot?: FrozenInputSnapshot | null;
  frozen?: boolean;
}) {
  const t = useT();
  const correctiveActions = [...new Set((readiness.quota_decision.errors ?? []).flatMap((item) => item.corrective_actions ?? []))];
  const modules = snapshot?.modules ?? Object.entries(project?.modules ?? {}).map(([slot, module_id]) => ({ slot, module_id, module_version: t("readinessEvidence.moduleVersion"), contract_version: t("readinessEvidence.contractVersion"), source_sha256: t("readinessEvidence.sourceHash") }));
  return <section className={`readiness-evidence ${readiness.quota_decision.accepted ? "accepted" : "blocked"}`} aria-label={t(frozen ? "readinessEvidence.frozenLabel" : "readinessEvidence.checkLabel")}>
    <header><div><span>{t(frozen ? "readinessEvidence.frozenKicker" : "readinessEvidence.checkKicker")}</span><h4>{t(frozen ? "readinessEvidence.frozenTitle" : "readinessEvidence.checkTitle")}</h4></div><Badge tone={readiness.quota_decision.accepted ? "good" : "warn"}>{t(readiness.quota_decision.accepted ? "readinessEvidence.pass" : "readinessEvidence.fail")}</Badge></header>
    <div className="readiness-evidence-grid">
      <article><small>{t("readinessEvidence.trace")}</small><b>{t(readiness.trace_profile === "full" ? "readinessEvidence.trace.full" : readiness.trace_profile === "off" ? "readinessEvidence.trace.off" : "readinessEvidence.trace.summary")}</b></article>
      <article><small>{t("readinessEvidence.persisted")}</small><b>{formatBytes(readiness.estimate.persisted_bytes)}</b></article>
      <article><small>{t("readinessEvidence.temporary")}</small><b>{formatBytes(readiness.estimate.temporary_bytes)}</b></article>
      <article><small>{t("readinessEvidence.reserve")}</small><b>{formatBytes(readiness.estimate.reserve_bytes)}</b></article>
      <article><small>{t("readinessEvidence.free")}</small><b>{formatBytes(readiness.free_space_observation.free_bytes)}</b></article>
      <article><small>{t("readinessEvidence.runtime")}</small><b>{formatNumber(readiness.estimate.runtime_seconds, 0) === "—" ? "—" : t("readinessEvidence.seconds", { value: formatNumber(readiness.estimate.runtime_seconds, 0) })}</b></article>
    </div>
    <dl className="readiness-identities">
      <div><dt>{t("readinessEvidence.dataPack")}</dt><dd><code>{project?.data_pack_id ?? t("readinessEvidence.dataPackFrozen")}</code></dd></div>
      <div><dt>{snapshot?.pack_manifest_sha256 ? frozenManifestLabel() : t("readinessEvidence.fingerprint")}</dt><dd><code>{snapshot?.pack_manifest_sha256 ?? readiness.calibration_key.data_fingerprint ?? t("readinessEvidence.fingerprintMissing")}</code>{snapshot?.pack_manifest_sha256 && <small className="readiness-identity-note">{frozenManifestNote()}</small>}</dd></div>
      <div><dt>{t("readinessEvidence.networkPack")}</dt><dd><code>{snapshot?.network_pack_id ?? project?.market_configuration?.network_pack_id ?? t("readinessEvidence.notSelected")}</code></dd></div>
      {snapshot?.network_pack_manifest_sha256 && <div><dt>{t("readinessEvidence.networkManifest")}</dt><dd><code>{snapshot.network_pack_manifest_sha256}</code></dd></div>}
      <div><dt>{t("readinessEvidence.runContext")}</dt><dd><code>{readiness.run_context_sha256}</code></dd></div>
      <div><dt>{t("readinessEvidence.yearContext")}</dt><dd><code>{readiness.year_context_sha256}</code></dd></div>
      <div><dt>{t("readinessEvidence.basis")}</dt><dd>{readiness.calibration_basis.source ?? t("readinessEvidence.basisDefault")}{readiness.calibration_basis.calibration_periods ? t("readinessEvidence.calibration", { count: readiness.calibration_basis.calibration_periods }) : ""}</dd></div>
      <div><dt>{t("readinessEvidence.solver")}</dt><dd><code>{project?.solver_contract ? `${project.solver_contract.method} · ${project.solver_contract.contract_version}` : readiness.calibration_key.solver_fingerprint ?? t("readinessEvidence.solverDefault")}</code></dd></div>
    </dl>
    <details><summary>{t("readinessEvidence.modules")}</summary>{modules.map((module) => <div className="readiness-module" key={`${module.slot}-${module.module_id}`}><b>{module.slot}</b><code>{module.module_id} · {module.module_version} · {module.contract_version}</code><small>{module.source_sha256}</small></div>)}</details>
    {!readiness.quota_decision.accepted && <div className="readiness-corrections"><b>{t("readinessEvidence.corrections")}</b>{correctiveActions.map((action) => <span key={action}>{action}</span>)}</div>}
  </section>;
}
