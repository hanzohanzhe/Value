import {
  type VRECurtailmentValues,
  formatOptionalNetworkNumber,
} from "./networkRedispatch";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey, Translate } from "../../i18n/index.ts";

type SignedStep = {
  key: keyof Pick<
    VRECurtailmentValues,
    | "economic_mwh"
    | "forecast_added_mwh"
    | "forecast_avoided_mwh"
    | "redispatch_added_mwh"
    | "redispatch_avoided_mwh"
  >;
  label: MessageKey;
  direction: "addition" | "avoidance";
};

const steps: SignedStep[] = [
  { key: "economic_mwh", label: "network.waterfall.economic", direction: "addition" },
  { key: "forecast_added_mwh", label: "network.waterfall.forecastAdded", direction: "addition" },
  { key: "forecast_avoided_mwh", label: "network.waterfall.forecastAvoided", direction: "avoidance" },
  { key: "redispatch_added_mwh", label: "network.waterfall.redispatchAdded", direction: "addition" },
  { key: "redispatch_avoided_mwh", label: "network.waterfall.redispatchAvoided", direction: "avoidance" },
];

function signedMwh(t: Translate, value: number | null, direction: SignedStep["direction"]): string {
  const formatted = formatOptionalNetworkNumber(value);
  if (formatted == null) return t("network.value.unavailable");
  return `${direction === "avoidance" ? "−" : "+"}${formatted} MWh`;
}

export default function CurtailmentWaterfall({ values }: { values: VRECurtailmentValues }) {
  const t = useT();
  const finiteValues = steps
    .map((step) => values[step.key])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const maximum = Math.max(...finiteValues.map(Math.abs), 1);
  const finalTotal = formatOptionalNetworkNumber(values.total_mwh);

  return <div className="curtailment-waterfall">
    <ol aria-label={t("network.waterfall.label")}>
      {steps.map((step) => {
        const value = values[step.key];
        const width = typeof value === "number" && Number.isFinite(value)
          ? `${Math.abs(value) / maximum * 100}%`
          : "0%";
        return <li className={step.direction} key={step.key}>
          <div>
            <span>{t(step.label)}</span>
            <small>{t(step.direction === "avoidance" ? "network.waterfall.decrease" : "network.waterfall.increase")}</small>
          </div>
          <span className="curtailment-step-track" aria-hidden="true"><i style={{ width }} /></span>
          <b>{signedMwh(t, value, step.direction)}</b>
        </li>;
      })}
    </ol>
    <div className="curtailment-waterfall-total">
      <span><small>{t("network.waterfall.reconciled")}</small><b>{t("network.waterfall.final")}</b></span>
      <strong>{finalTotal == null ? t("network.value.unavailable") : `${finalTotal} MWh`}</strong>
    </div>
  </div>;
}
