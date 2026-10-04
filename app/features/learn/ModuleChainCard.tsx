import type { Value101ModuleIdentity } from "./value101";

const plainPurpose: Record<string, string> = {
  pipeline: "Advances projects already in planning and records which are commissioned, delayed or unsuccessful.",
  storage_cost: "Turns the selected storage cost-recovery method into offers used by market clearing.",
  psm: "Clears the bid-at-cost power market for each half-hour and records dispatch, storage and unused renewable energy.",
  vre_cap: "Limits how much new solar and wind capacity may enter the investment process.",
  storage_cap: "Limits new storage investment while retaining technology-specific power and energy capacity.",
  investment: "Lets economic owners assess investment using the market evidence produced by the PSM.",
  transition: "Carries commissioned assets, storage state and planning records into the next model year.",
};

export default function ModuleChainCard({
  module,
  sequence,
}: {
  module: Value101ModuleIdentity;
  sequence: number;
}) {
  return <article className="value101-module-card">
    <header>
      <i>{String(sequence).padStart(2, "0")}</i>
      <div><span>{module.slot.replaceAll("_", " ")}</span><h4>{module.name}</h4></div>
    </header>
    <p>{plainPurpose[module.slot] ?? module.description ?? "A selected step in the VALUE model chain."}</p>
    <details>
      <summary>Technical disclosure</summary>
      <dl>
        <div><dt>Module ID</dt><dd><code>{module.id}</code></dd></div>
        <div><dt>Version</dt><dd>{module.version}</dd></div>
        <div><dt>Contract</dt><dd><code>{module.contract_version ?? "Not declared"}</code></dd></div>
        <div><dt>Source location</dt><dd><code>{module.implementation ?? "Not declared by registry"}</code></dd></div>
      </dl>
      <div className="value101-module-io">
        <section><b>Inputs</b>{module.inputs.map((item) => <code key={item}>{item}</code>)}</section>
        <section><b>Outputs</b>{module.outputs.map((item) => <code key={item}>{item}</code>)}</section>
      </div>
    </details>
  </article>;
}
