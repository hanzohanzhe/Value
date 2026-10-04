import type { Project } from "../studies/types";
import type { ResourceReadiness, FrozenInputSnapshot } from "../runs/types";
import { Badge, formatBytes, formatNumber } from "../shared/presentation";

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
  const correctiveActions = [...new Set((readiness.quota_decision.errors ?? []).flatMap((item) => item.corrective_actions ?? []))];
  const modules = snapshot?.modules ?? Object.entries(project?.modules ?? {}).map(([slot, module_id]) => ({ slot, module_id, module_version: "saved Study revision", contract_version: "registry resolved", source_sha256: "bound into module fingerprint" }));
  return <section className={`readiness-evidence ${readiness.quota_decision.accepted ? "accepted" : "blocked"}`} aria-label={frozen ? "Frozen run readiness evidence" : "Check readiness evidence"}>
    <header><div><span>{frozen ? "Immutable run evidence" : "Backend readiness evidence"}</span><h4>{frozen ? "Frozen before model execution" : "Exact selected graph and resource gate"}</h4></div><Badge tone={readiness.quota_decision.accepted ? "good" : "warn"}>{readiness.quota_decision.accepted ? "Pass" : "Fail"}</Badge></header>
    <div className="readiness-evidence-grid">
      <article><small>Recorded trace</small><b>{readiness.trace_profile === "full" ? "Full market replay" : readiness.trace_profile === "off" ? "Advanced: Off" : "Summary"}</b></article>
      <article><small>Estimated persisted output</small><b>{formatBytes(readiness.estimate.persisted_bytes)}</b></article>
      <article><small>Temporary space</small><b>{formatBytes(readiness.estimate.temporary_bytes)}</b></article>
      <article><small>Free-space reserve</small><b>{formatBytes(readiness.estimate.reserve_bytes)}</b></article>
      <article><small>Observed free space</small><b>{formatBytes(readiness.free_space_observation.free_bytes)}</b></article>
      <article><small>Estimated runtime</small><b>{formatNumber(readiness.estimate.runtime_seconds, 0)} seconds</b></article>
    </div>
    <dl className="readiness-identities">
      <div><dt>Data pack ID</dt><dd><code>{project?.data_pack_id ?? "recorded in frozen project"}</code></dd></div>
      <div><dt>{snapshot?.pack_manifest_sha256 ? "Data pack manifest SHA-256" : "Data fingerprint"}</dt><dd><code>{snapshot?.pack_manifest_sha256 ?? readiness.calibration_key.data_fingerprint ?? "not exposed by this preflight"}</code></dd></div>
      <div><dt>Network pack ID</dt><dd><code>{snapshot?.network_pack_id ?? project?.market_configuration?.network_pack_id ?? "not selected"}</code></dd></div>
      {snapshot?.network_pack_manifest_sha256 && <div><dt>Network pack manifest SHA-256</dt><dd><code>{snapshot.network_pack_manifest_sha256}</code></dd></div>}
      <div><dt>Run context SHA-256</dt><dd><code>{readiness.run_context_sha256}</code></dd></div>
      <div><dt>Opening year context SHA-256</dt><dd><code>{readiness.year_context_sha256}</code></dd></div>
      <div><dt>Runtime basis</dt><dd>{readiness.calibration_basis.source ?? "selected graph estimate"}{readiness.calibration_basis.calibration_periods ? ` · ${readiness.calibration_basis.calibration_periods} calibration periods` : ""}</dd></div>
      <div><dt>Solver identity</dt><dd><code>{project?.solver_contract ? `${project.solver_contract.method} · ${project.solver_contract.contract_version}` : readiness.calibration_key.solver_fingerprint ?? "registry default"}</code></dd></div>
    </dl>
    <details><summary>Selected module identities</summary>{modules.map((module) => <div className="readiness-module" key={`${module.slot}-${module.module_id}`}><b>{module.slot}</b><code>{module.module_id} · {module.module_version} · {module.contract_version}</code><small>{module.source_sha256}</small></div>)}</details>
    {!readiness.quota_decision.accepted && <div className="readiness-corrections"><b>Corrective actions</b>{correctiveActions.map((action) => <span key={action}>{action}</span>)}</div>}
  </section>;
}
