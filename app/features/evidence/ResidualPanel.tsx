"use client";

// F-P04-5 (designer ruling 2026-10-06): the raw boundary residual of the
// energy-balance check, shown only here in Inspect. The status bar shows the
// A2 gate verdict; the raw verdict is evidence, not a second status.
import { rawResidualRows, type EnergyBalanceRecord } from "../workspace/runValidation.ts";
import { ValueState } from "../shared/Callout";
import "./residual-panel.css";

export default function ResidualPanel({ balance }: { balance?: EnergyBalanceRecord | null }) {
  const rows = rawResidualRows(balance);
  return <section className="panel residual-panel value-new-control" aria-label="Energy-balance residuals">
    <div className="panel-head"><div><span>ENERGY-BALANCE RESIDUALS</span><h3>Raw boundary check</h3></div></div>
    {!rows ? <p className="residual-panel-note">This Run did not record an energy-balance report.</p> : <>
      <div className="table-scroll"><table className="residual-table"><thead><tr><th>Boundary</th><th>Raw status</th><th>Max residual</th><th>Periods</th></tr></thead>
        <tbody>{rows.map((row) => <tr key={row.boundary}><td><code>{row.boundary}</code></td><td>{row.rawStatus}</td><td>{row.maxResidual ?? <ValueState state="not_recorded" />}</td><td>{row.periods ?? <ValueState state="not_recorded" />}</td></tr>)}</tbody></table></div>
      <p className="residual-panel-note">The raw verdict is evidence before stress shortfalls are booked as unserved energy (decision A2). The status bar shows the gate, which books them.</p>
    </>}
  </section>;
}
