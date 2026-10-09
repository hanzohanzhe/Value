"use client";

// The zonal solver contract of a Study (Review step).  Wording from the
// dictionaries (studies.solver.*, P1 spec 3); setting names in code stay as they are.
import { isBuiltinZonalSolverContract, isLegacyZonalSolverContract, withZonalSolverContractFlags, zonalSolverContractGeneration, zonalSolverContractUpgradeChanges, type ZonalSolverContract } from "../network/networkRedispatch";
import { Badge } from "../shared/presentation";
import { useT } from "../../i18n/LocaleProvider";

const SOLVER_METHODS: ZonalSolverContract["method"][] = ["highs-ds", "highs-ipm", "highs"];

export default function SolverSettingsEditor({
  contract,
  useCustom,
  acknowledgement,
  error,
  onUseCustom,
  onChange,
  onAcknowledgement,
  onUpgrade,
}: {
  contract: ZonalSolverContract;
  useCustom: boolean;
  acknowledgement: boolean;
  error: string;
  onUseCustom: (enabled: boolean) => void;
  onChange: (contract: ZonalSolverContract) => void;
  onAcknowledgement: (checked: boolean) => void;
  onUpgrade: () => void;
}) {
  const t = useT();
  const legacy = isLegacyZonalSolverContract(contract);
  const generation = zonalSolverContractGeneration(contract);
  const historicalLabel = generation === "v2" ? "v2" : t("studies.solver.gbp1Lock");
  const builtin = isBuiltinZonalSolverContract(contract);
  const update = <K extends keyof ZonalSolverContract>(key: K, value: ZonalSolverContract[K]) => {
    const next = { ...contract, [key]: value };
    onChange(withZonalSolverContractFlags(next));
  };
  const updateCeiling = (key: string, value: number) => update(
    "validated_ceilings",
    { ...contract.validated_ceilings, [key]: value },
  );
  return <section className="solver-settings-editor" aria-label={t("studies.solver.title")}>
    <header><div><span>{t("studies.solver.kicker")}</span><h4>{t("studies.solver.title")}</h4></div><Badge tone={builtin ? "blue" : "warn"}>{legacy ? t("studies.solver.historicalPolicy", { label: historicalLabel }) : builtin ? t("studies.solver.builtin") : t("studies.solver.custom")}</Badge></header>
    <p>{t("studies.solver.lead")}</p>
    {legacy && <div className="info-box"><b>{t("studies.solver.legacyTitle", { label: historicalLabel })}</b><p>{t("studies.solver.legacyBody")}</p><div className="table-scroll"><table className="solver-upgrade-preview" aria-label={t("studies.solver.upgradeTable")}><thead><tr><th>{t("studies.solver.setting")}</th><th>{t("studies.solver.recorded")}</th><th>{t("studies.solver.current")}</th></tr></thead><tbody>{zonalSolverContractUpgradeChanges(contract).map((row) => <tr key={row.field}><td><code>{row.field}</code></td><td>{row.recorded}</td><td>{row.current}</td></tr>)}</tbody></table></div><button type="button" className="secondary" onClick={onUpgrade}>{t("studies.solver.upgrade")}</button></div>}
    {!legacy && <label className="solver-custom-toggle"><input type="checkbox" checked={useCustom} onChange={(event) => onUseCustom(event.target.checked)} /><span><b>{t("studies.solver.useCustom")}</b><small>{t("studies.solver.useCustomNote")}</small></span></label>}
    <fieldset disabled={!useCustom || legacy}>
      <legend>{t("studies.solver.editable")}</legend>
      <div className="solver-settings-grid">
        <label><span>{t("studies.solver.method")}</span><select value={contract.method} onChange={(event) => update("method", event.target.value as ZonalSolverContract["method"])}>{SOLVER_METHODS.map((method) => <option value={method} key={method}>{method}</option>)}</select></label>
        <label><span>{t("studies.solver.primal")}</span><input type="number" min="1e-10" max="1e-7" step="any" value={contract.primal_feasibility_tolerance} onChange={(event) => update("primal_feasibility_tolerance", Number(event.target.value))} /></label>
        <label><span>{t("studies.solver.dual")}</span><input type="number" min="1e-10" max="1e-7" step="any" value={contract.dual_feasibility_tolerance} onChange={(event) => update("dual_feasibility_tolerance", Number(event.target.value))} /></label>
        <label><span>{t("studies.solver.ipm")}</span><input type="number" min="1e-12" max="1e-7" step="any" value={contract.ipm_optimality_tolerance} onChange={(event) => update("ipm_optimality_tolerance", Number(event.target.value))} /></label>
        <label><span>{t("studies.solver.warning")}</span><input type="number" min="0" max="1" step="0.01" value={contract.warning_fraction} onChange={(event) => update("warning_fraction", Number(event.target.value))} /><small>{t("studies.solver.warningNote")}</small></label>
        <label><span>{t("studies.solver.bidCeiling")}</span><input type="number" value={contract.validated_ceilings.primary_bid_cost_gbp} readOnly aria-readonly="true" /><small>{generation === "v2" ? t("studies.solver.bidCeilingV2") : t("studies.solver.bidCeilingFixed")}</small></label>
        <label><span>{t("studies.solver.deviationCeiling")}</span><input type="number" min="0" max="0.01" step="any" value={contract.validated_ceilings.secondary_schedule_deviation_mwh} onChange={(event) => updateCeiling("secondary_schedule_deviation_mwh", Number(event.target.value))} /><small>{t("studies.solver.perHalfHour")}</small></label>
        <label><span>{t("studies.solver.throughputCeiling")}</span><input type="number" min="0" max="0.01" step="any" value={contract.validated_ceilings.physical_throughput_mwh} onChange={(event) => updateCeiling("physical_throughput_mwh", Number(event.target.value))} /><small>{t("studies.solver.perHalfHour")}</small></label>
      </div>
    </fieldset>
    <aside className="solver-execution-ceilings"><b>{t("studies.solver.platformTitle")}</b><p>{t("studies.solver.platformLead")}</p><dl><div><dt>{t("studies.solver.platformBid")}</dt><dd>{generation === "v2" ? t("studies.solver.platformBidV2") : t("studies.solver.platformBidV4")}</dd></div><div><dt>{t("studies.solver.platformDeviation")}</dt><dd>{t("studies.solver.platformMwh")}</dd></div><div><dt>{t("studies.solver.platformThroughput")}</dt><dd>{t("studies.solver.platformMwh")}</dd></div></dl><small>{t("studies.solver.platformNote")}</small></aside>
    {error && <p className="solver-settings-error" role="alert">{error}</p>}
    {!legacy && contract.requires_acknowledgement && <label className="solver-acknowledgement"><input type="checkbox" checked={acknowledgement} onChange={(event) => onAcknowledgement(event.target.checked)} /><span>{t("studies.solver.acknowledgement")}</span></label>}
  </section>;
}
