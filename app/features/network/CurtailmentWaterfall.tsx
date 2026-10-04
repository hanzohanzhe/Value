import {
  type VRECurtailmentValues,
  formatOptionalNetworkNumber,
} from "./networkRedispatch";

type SignedStep = {
  key: keyof Pick<
    VRECurtailmentValues,
    | "economic_mwh"
    | "forecast_added_mwh"
    | "forecast_avoided_mwh"
    | "redispatch_added_mwh"
    | "redispatch_avoided_mwh"
  >;
  label: string;
  direction: "addition" | "avoidance";
};

const steps: SignedStep[] = [
  { key: "economic_mwh", label: "Economic curtailment", direction: "addition" },
  { key: "forecast_added_mwh", label: "Forecast added", direction: "addition" },
  { key: "forecast_avoided_mwh", label: "Forecast avoided", direction: "avoidance" },
  { key: "redispatch_added_mwh", label: "Redispatch added", direction: "addition" },
  { key: "redispatch_avoided_mwh", label: "Redispatch avoided", direction: "avoidance" },
];

function signedMwh(value: number | null, direction: SignedStep["direction"]): string {
  const formatted = formatOptionalNetworkNumber(value);
  if (formatted == null) return "Unavailable";
  return `${direction === "avoidance" ? "−" : "+"}${formatted} MWh`;
}

export default function CurtailmentWaterfall({ values }: { values: VRECurtailmentValues }) {
  const finiteValues = steps
    .map((step) => values[step.key])
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const maximum = Math.max(...finiteValues.map(Math.abs), 1);
  const finalTotal = formatOptionalNetworkNumber(values.total_mwh);

  return <div className="curtailment-waterfall">
    <ol aria-label="Five signed VRE curtailment attribution steps">
      {steps.map((step) => {
        const value = values[step.key];
        const width = typeof value === "number" && Number.isFinite(value)
          ? `${Math.abs(value) / maximum * 100}%`
          : "0%";
        return <li className={step.direction} key={step.key}>
          <div>
            <span>{step.label}</span>
            <small>{step.direction === "avoidance" ? "Decrease (−)" : "Increase (+)"}</small>
          </div>
          <span className="curtailment-step-track" aria-hidden="true"><i style={{ width }} /></span>
          <b>{signedMwh(value, step.direction)}</b>
        </li>;
      })}
    </ol>
    <div className="curtailment-waterfall-total">
      <span><small>Reconciled result</small><b>Final VRE curtailment</b></span>
      <strong>{finalTotal == null ? "Unavailable" : `${finalTotal} MWh`}</strong>
    </div>
  </div>;
}
