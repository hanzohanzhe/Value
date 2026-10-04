import type { DataSourceDefinition, SourceRevision } from "./types";

type Props = {
  sources: DataSourceDefinition[];
  currentRevision: (sourceId: string) => SourceRevision | undefined;
  busy: boolean;
  start: (operation: "discover" | "fetch", input: Record<string, unknown>) => Promise<void>;
};

export function OfficialSources({ sources, currentRevision, busy, start }: Props) {
  return <><div className="data-workbench-actions"><button className="secondary" disabled={busy} onClick={() => void start("discover", { source_ids: [] })}>Check official catalogues</button><small>Discovery reads metadata only. It never replaces an installed benchmark.</small></div><div className="source-review-list">{sources.map((source) => {
    const revision = currentRevision(source.source_id);
    return <article key={source.source_id}><header><div><span>{source.authority}</span><h4>{source.semantic_role.replaceAll("_", " ")}</h4></div><em className={`source-state ${revision?.status ?? "not-checked"}`}>{revision?.status?.replaceAll("_", " ") ?? "not checked"}</em></header><p>{source.candidate_uses.join(" · ")}</p><small>{source.licence_expected}</small>{revision && <div className="source-revision"><code>{revision.revision_id}</code><span>{revision.redistribution_decision === "needs_rights_review" ? "bytes pinned · rights review pending" : revision.publication_date || "date not supplied"}</span><button className="text-button" disabled={revision.status === "unavailable" || Boolean(revision.object_key)} onClick={() => void start("fetch", { schema_version: "value.data-fetch-request/v1", revision })}>{revision.object_key ? "Pinned" : "Fetch reviewed revision"}</button></div>}</article>;
  })}</div></>;
}
