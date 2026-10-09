"use client";

// One module of the VALUE 101 baseline chain, with its live registry identity
// in a technical disclosure.  Wording from the dictionaries (learn.module.*).
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/index.ts";
import type { Value101ModuleIdentity } from "./value101";

const PURPOSE_SLOTS = new Set(["pipeline", "storage_cost", "psm", "vre_cap", "storage_cap", "investment", "transition"]);

export default function ModuleChainCard({
  module,
  sequence,
}: {
  module: Value101ModuleIdentity;
  sequence: number;
}) {
  const t = useT();
  const purpose = PURPOSE_SLOTS.has(module.slot) ? t(`learn.module.${module.slot}` as MessageKey) : module.description ?? t("learn.module.fallback");
  return <article className="value101-module-card">
    <header>
      <i>{String(sequence).padStart(2, "0")}</i>
      <div><span>{module.slot.replaceAll("_", " ")}</span><h4>{module.name}</h4></div>
    </header>
    <p>{purpose}</p>
    <details>
      <summary>{t("learn.module.disclosure")}</summary>
      <dl>
        <div><dt>{t("learn.module.id")}</dt><dd><code>{module.id}</code></dd></div>
        <div><dt>{t("learn.module.version")}</dt><dd>{module.version}</dd></div>
        <div><dt>{t("learn.module.contract")}</dt><dd><code>{module.contract_version ?? t("learn.module.notDeclared")}</code></dd></div>
        <div><dt>{t("learn.module.source")}</dt><dd><code>{module.implementation ?? t("learn.module.notDeclaredRegistry")}</code></dd></div>
      </dl>
      <div className="value101-module-io">
        <section><b>{t("learn.module.inputs")}</b>{module.inputs.map((item) => <code key={item}>{item}</code>)}</section>
        <section><b>{t("learn.module.outputs")}</b>{module.outputs.map((item) => <code key={item}>{item}</code>)}</section>
      </div>
    </details>
  </article>;
}
