"use client";

import { EmptyState } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import type { InstalledBundle } from "./types";

// P1 W4b: dictionaries (dataWorkbench.installed.*); an empty list says why and what comes next (EmptyState).
export function InstalledPacks({ bundles }: { bundles: InstalledBundle[] }) {
  const t = useT();
  return <div className="data-workbench-grid">{bundles.length ? bundles.map((bundle) => <article key={bundle.pack_id}>
    <span>{t("dataWorkbench.installed.badge")}</span><h4>{bundle.name ?? bundle.pack_id}</h4><code>{bundle.pack_id}</code>
    <p>{t("dataWorkbench.installed.interfaces", { passed: bundle.validation.passed, total: bundle.validation.total })}</p>
    <small>{bundle.installation_boundary.replaceAll("_", " ")}</small>
  </article>) : <EmptyState className="data-workbench-empty" title={t("dataWorkbench.installed.empty")}>{t("dataWorkbench.installed.emptyBody")}</EmptyState>}</div>;
}
