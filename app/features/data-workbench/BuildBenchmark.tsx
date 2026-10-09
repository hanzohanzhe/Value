"use client";

import { Button } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";

type Props = {
  pinnedCount: number;
  sourceCount: number;
  allPinned: boolean;
  busy: boolean;
  start: (operation: "compile", input: Record<string, unknown>) => Promise<void>;
};

// P1 W4b: dictionaries (dataWorkbench.build.*); the build creates an experimental candidate, never an installed pack.
export function BuildBenchmark({ pinnedCount, sourceCount, allPinned, busy, start }: Props) {
  const t = useT();
  return <div className="build-benchmark"><div><span>{t("dataWorkbench.build.eyebrow")}</span><h4>{t("dataWorkbench.build.title")}</h4><p>{t("dataWorkbench.build.body")}</p></div><dl><div><dt>{t("dataWorkbench.build.pinned")}</dt><dd>{pinnedCount} / {sourceCount}</dd></div><div><dt>{t("dataWorkbench.build.identity")}</dt><dd>{t("dataWorkbench.build.unsigned")}</dd></div><div><dt>{t("dataWorkbench.build.claim")}</dt><dd>{t("dataWorkbench.build.claimValue")}</dd></div></dl><Button variant="primary" disabled={!allPinned || busy} disabledReason={busy ? t("dataWorkbench.job.busy") : t("dataWorkbench.build.blocked")} onClick={() => void start("compile", { schema_version: "value.data-compile-request/v1", recipe_id: "prompt98-gb-zonal", inventory_key: "official-uk-network-v1.json", candidate_name: "gb-zonal-official-candidate" })}>{t("dataWorkbench.build.action")}</Button>{!allPinned && <small>{t("dataWorkbench.build.blocked")}</small>}</div>;
}
