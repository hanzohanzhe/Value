import { formatNetworkNumber, numberValue, scaled } from "./networkRedispatch";
import { withUnit } from "../shared/format.ts";
import { FLOW_ARROWS, flowDirection } from "./boundaryView.ts";
import { useT } from "../../i18n/LocaleProvider";

type Row = Record<string, unknown>;

/** F3-13 (display part, W4c): a signed transfer with its direction arrow, "—" when missing. */
function transferLabel(value: number | null): string {
  const direction = flowDirection(value);
  return direction == null || value == null ? withUnit(formatNetworkNumber(null), "MWh") : `${FLOW_ARROWS[direction]} ${withUnit(formatNetworkNumber(Math.abs(value)), "MWh")}`;
}

export default function NetworkZoneMap({ zones, boundaries }: { zones: Row[]; boundaries: Row[] }) {
  const t = useT();
  return <figure className="network-computational-map" aria-label={t("network.map.label")}>
    <figcaption>
      <span>{t("network.map.kicker")}</span>
      <b>{t("network.map.title")}</b>
      <small>{t("network.map.note")}</small>
    </figcaption>
    {/* F3-13: what the signs mean (the ledger gives no corridor endpoints, so no arrow is drawn between zones). */}
    <dl className="network-flow-legend">
      <div><dt>{t("network.map.directionTerm")}</dt><dd>{t("network.map.directionBody")}</dd></div>
      <div><dt>{t("network.map.netTerm")}</dt><dd>{t("network.map.netBody")}</dd></div>
    </dl>
    <div className="network-schematic-grid">
      <div className="network-zone-stack" aria-label={t("network.map.zones")}>
      {zones.map((zone) => <div className="network-zone-node" key={String(zone.zone_id)}>
        <article>
          <b>{String(zone.zone_id)}</b>
          <small>{t("network.map.demand", { value: withUnit(formatNetworkNumber(numberValue(zone, "demand_mwh")), "MWh") })}</small>
          <em>{t("network.map.netPosition", { value: withUnit(formatNetworkNumber(numberValue(zone, "net_position_mwh")), "MWh") })}</em>
          <small>{t("network.map.loadShed", { value: withUnit(formatNetworkNumber(numberValue(zone, "load_shedding_mwh")), "MWh") })}</small>
        </article>
      </div>)}
      </div>
      <div className="network-corridor-stack" aria-label={t("network.map.corridors")}>
        <b>{t("network.map.corridors")}</b>
        {boundaries.map((boundary) => <aside key={String(boundary.boundary_id)}>
          <strong>{String(boundary.boundary_id)}</strong>
          <span>{t("network.map.transfer", { value: transferLabel(numberValue(boundary, "transfer_mwh")) })}</span>
          <small>{t("network.map.used", { value: withUnit(formatNetworkNumber(scaled(numberValue(boundary, "utilisation_fraction"), 100), 1), "%", "") })}</small>
        </aside>)}
        <small>{t("network.map.topology")}</small>
      </div>
    </div>
  </figure>;
}
