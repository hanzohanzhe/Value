"use client";

import { Button } from "../../ui";
import { useT } from "../../i18n/LocaleProvider";
import type { DataSourceDefinition, SourceRevision } from "./types";

type Props = {
  sources: DataSourceDefinition[];
  currentRevision: (sourceId: string) => SourceRevision | undefined;
  busy: boolean;
  start: (operation: "discover" | "fetch", input: Record<string, unknown>) => Promise<void>;
};

// P1 W4b: dictionaries (dataWorkbench.sources.*); F4-05: a running job blocks Fetch as well as Discover.
export function OfficialSources({ sources, currentRevision, busy, start }: Props) {
  const t = useT();
  return <><div className="data-workbench-actions"><Button disabled={busy} disabledReason={t("dataWorkbench.job.busy")} onClick={() => void start("discover", { source_ids: [] })}>{t("dataWorkbench.sources.discover")}</Button><small>{t("dataWorkbench.sources.discoverNote")}</small></div><div className="source-review-list">{sources.map((source) => {
    const revision = currentRevision(source.source_id);
    const unavailable = revision?.status === "unavailable" || Boolean(revision?.object_key);
    return <article key={source.source_id}><header><div><span>{source.authority}</span><h4>{source.semantic_role.replaceAll("_", " ")}</h4></div><em className={`source-state ${revision?.status ?? "not-checked"}`}>{revision?.status?.replaceAll("_", " ") ?? t("dataWorkbench.sources.notChecked")}</em></header><p>{source.candidate_uses.join(" · ")}</p><small>{source.licence_expected}</small>{revision && <div className="source-revision"><code>{revision.revision_id}</code><span>{revision.redistribution_decision === "needs_rights_review" ? t("dataWorkbench.sources.rightsPending") : revision.publication_date || t("dataWorkbench.sources.noDate")}</span><Button size="sm" variant="ghost" disabled={busy || unavailable} disabledReason={busy ? t("dataWorkbench.job.busy") : t("dataWorkbench.sources.fetchUnavailable")} onClick={() => void start("fetch", { schema_version: "value.data-fetch-request/v1", revision })}>{revision.object_key ? t("dataWorkbench.sources.pinned") : t("dataWorkbench.sources.fetch")}</Button></div>}</article>;
  })}</div></>;
}
