import { formatNetworkNumber, numberValue, scaled } from "./networkRedispatch";
import { withUnit } from "../shared/format.ts";

type Row = Record<string, unknown>;

export default function NetworkZoneMap({ zones, boundaries }: { zones: Row[]; boundaries: Row[] }) {
  return <figure className="network-computational-map" aria-label="Computational zone and corridor schematic">
    <figcaption>
      <span>Computational schematic</span>
      <b>Zones connected by constrained corridors</b>
      <small>Positions are schematic. They do not represent electrical substations or line routes.</small>
    </figcaption>
    <div className="network-schematic-grid">
      <div className="network-zone-stack" aria-label="Zones">
      {zones.map((zone) => <div className="network-zone-node" key={String(zone.zone_id)}>
        <article>
          <b>{String(zone.zone_id)}</b>
          <small>{withUnit(formatNetworkNumber(numberValue(zone, "demand_mwh")), "MWh")} demand</small>
          <em>{withUnit(formatNetworkNumber(numberValue(zone, "net_position_mwh")), "MWh")} net position</em>
        </article>
      </div>)}
      </div>
      <div className="network-corridor-stack" aria-label="Computational corridors">
        <b>Computational corridors</b>
        {boundaries.map((boundary) => <aside key={String(boundary.boundary_id)}>
          <strong>{String(boundary.boundary_id)}</strong>
          <span>{withUnit(formatNetworkNumber(numberValue(boundary, "transfer_mwh")), "MWh")} transfer</span>
          <small>{withUnit(formatNetworkNumber(scaled(numberValue(boundary, "utilisation_fraction"), 100), 1), "%", "")} used</small>
        </aside>)}
        <small>Topology is defined by the signed network pack; this ledger view does not infer endpoints from table order.</small>
      </div>
    </div>
  </figure>;
}
