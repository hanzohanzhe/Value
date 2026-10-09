"use client";

import { Disclosure } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/index.ts";

// The data adapter guide (formerly "Add data · Adapter guide"; W3 placed it on
// /extensions). P1 W4b (D-W3-5): it is about bringing data in, so it is the last
// section of /data, collapsed by default (it is reference material, R3-06).
const STEPS: readonly [string, MessageKey, MessageKey][] = [
  ["01", "data.adapters.step1Title", "data.adapters.step1Body"],
  ["02", "data.adapters.step2Title", "data.adapters.step2Body"],
  ["03", "data.adapters.step3Title", "data.adapters.step3Body"],
  ["04", "data.adapters.step4Title", "data.adapters.step4Body"],
];
const EXAMPLE = `data_pack: my-country-2030
country: XX
timezone: Region/City
bindings:
  demand.real:
    source: demand.csv
    column: observed_mwh
    unit: MWh/period
  projects.repd:
    source: projects.parquet
    mapping:
      capacity_mw: size_mw
      technology: tech_code`;

export default function AdapterGuide() {
  const t = useT();
  return <section className="extension-adapter-guide" aria-labelledby="adapter-guide-title">
    <header className="page-section-head"><div><span>{t("data.adapters.eyebrow")}</span><h3 id="adapter-guide-title">{t("data.adapters.title")}</h3></div><p>{t("data.adapters.body")}</p></header>
    <Disclosure summary={t("data.adapters.show")}>
      <div className="adapter-steps">{STEPS.map(([number, title, copy]) => <article key={number}><i aria-hidden="true">{number}</i><h4>{t(title)}</h4><p>{t(copy)}</p></article>)}</div>
      <section className="panel contract-example"><div><span>{t("data.adapters.exampleEyebrow")}</span><h4>{t("data.adapters.exampleTitle")}</h4><p>{t("data.adapters.exampleBody")}</p></div><pre>{EXAMPLE}</pre></section>
    </Disclosure>
  </section>;
}
