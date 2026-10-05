import { isBuiltinZonalSolverContract, isLegacyZonalSolverContract, withZonalSolverContractFlags, zonalSolverContractGeneration, type ZonalSolverContract } from "../network/networkRedispatch";
import { Badge } from "../shared/presentation";

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
  const legacy = isLegacyZonalSolverContract(contract);
  const generation = zonalSolverContractGeneration(contract);
  const historicalLabel = generation === "v2" ? "v2" : "v3 GBP 1 lock";
  const builtin = isBuiltinZonalSolverContract(contract);
  const update = <K extends keyof ZonalSolverContract>(key: K, value: ZonalSolverContract[K]) => {
    const next = { ...contract, [key]: value };
    onChange(withZonalSolverContractFlags(next));
  };
  const updateCeiling = (key: string, value: number) => update(
    "validated_ceilings",
    { ...contract.validated_ceilings, [key]: value },
  );
  return <section className="solver-settings-editor" aria-label="Advanced solver settings">
    <header><div><span>Zonal numerical contract</span><h4>Advanced solver settings</h4></div><Badge tone={builtin ? "blue" : "warn"}>{legacy ? `Historical ${historicalLabel} policy` : builtin ? "Built-in v4 default settings" : "Custom v4 settings"}</Badge></header>
    <p>The four-phase zonal optimiser keeps physical feasibility strict. These controls change only its declared numerical lexicographic contract.</p>
    {legacy && <div className="info-box"><b>This draft retains its historical {historicalLabel} numerical policy.</b><p>Using the current v4 policy (load shedding locked first, numerical bid-cost lock, GBP 1 acceptance ceiling) changes the method. Saving records a new Study revision, clears the previous acknowledgement and requires a fresh review; the original revision and Run evidence retain their recorded policy. Results across these policies are not a comparison with identical methods.</p><button type="button" className="secondary" onClick={onUpgrade}>Use current v4 policy</button></div>}
    {!legacy && <label className="solver-custom-toggle"><input type="checkbox" checked={useCustom} onChange={(event) => onUseCustom(event.target.checked)} /><span><b>Use custom solver settings</b><small>Enable editing for this new Study revision.</small></span></label>}
    <fieldset disabled={!useCustom || legacy}>
      <legend>Editable solver contract</legend>
      <div className="solver-settings-grid">
        <label><span>Solver method</span><select value={contract.method} onChange={(event) => update("method", event.target.value as ZonalSolverContract["method"])}><option value="highs-ds">highs-ds</option><option value="highs-ipm">highs-ipm</option><option value="highs">highs</option></select></label>
        <label><span>Primal feasibility tolerance</span><input type="number" min="1e-10" max="1e-7" step="any" value={contract.primal_feasibility_tolerance} onChange={(event) => update("primal_feasibility_tolerance", Number(event.target.value))} /></label>
        <label><span>Dual feasibility tolerance</span><input type="number" min="1e-10" max="1e-7" step="any" value={contract.dual_feasibility_tolerance} onChange={(event) => update("dual_feasibility_tolerance", Number(event.target.value))} /></label>
        <label><span>IPM optimality tolerance</span><input type="number" min="1e-12" max="1e-7" step="any" value={contract.ipm_optimality_tolerance} onChange={(event) => update("ipm_optimality_tolerance", Number(event.target.value))} /></label>
        <label><span>Numerical warning threshold</span><input type="number" min="0" max="1" step="0.01" value={contract.warning_fraction} onChange={(event) => update("warning_fraction", Number(event.target.value))} /><small>Fraction of each validated ceiling; must be greater than zero.</small></label>
        <label><span>Redispatch bid cost validated ceiling</span><input type="number" value={contract.validated_ceilings.primary_bid_cost_gbp} readOnly aria-readonly="true" /><small>{generation === "v2" ? "Recorded v2 GBP total per half-hour" : "Fixed at GBP 1 total bid cost per solved half-hour period (acceptance ceiling)"}</small></label>
        <label><span>Schedule deviation validated ceiling</span><input type="number" min="0" max="0.01" step="any" value={contract.validated_ceilings.secondary_schedule_deviation_mwh} onChange={(event) => updateCeiling("secondary_schedule_deviation_mwh", Number(event.target.value))} /><small>MWh per half-hour</small></label>
        <label><span>Physical throughput validated ceiling</span><input type="number" min="0" max="0.01" step="any" value={contract.validated_ceilings.physical_throughput_mwh} onChange={(event) => updateCeiling("physical_throughput_mwh", Number(event.target.value))} /><small>MWh per half-hour</small></label>
      </div>
    </fieldset>
    <aside className="solver-execution-ceilings"><b>Immutable platform execution ceilings</b><p>These are explanatory limits and cannot be edited.</p><dl><div><dt>Redispatch bid cost</dt><dd>{generation === "v2" ? "Recorded v2: 0.10 GBP / half-hour" : "1.00 GBP total / solved half-hour period"}</dd></div><div><dt>Schedule deviation</dt><dd>0.01 MWh / half-hour</dd></div><div><dt>Physical throughput</dt><dd>0.01 MWh / half-hour</dd></div></dl><small>Presolve remains enabled. Execution never falls back automatically to another solver or to copperplate.</small></aside>
    {error && <p className="solver-settings-error" role="alert">{error}</p>}
    {!legacy && contract.requires_acknowledgement && <label className="solver-acknowledgement"><input type="checkbox" checked={acknowledgement} onChange={(event) => onAcknowledgement(event.target.checked)} /><span>Saving custom solver settings creates a new study revision and removes the built-in solver-validated label until the selected stack passes the validation gates.</span></label>}
  </section>;
}

