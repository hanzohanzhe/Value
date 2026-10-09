"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useState } from "react";
import { isExtensionResults, record, type ExtensionResults } from "./extension-results.types";
import "./ExtensionResultsPanel.css";
import { useT } from "../../i18n/LocaleProvider";

const LIMIT = 20;

export default function ExtensionResultsPanel({ runId }: { runId?: string }) {
  const t = useT();
  const text = (value: string | null) => value ?? t("extensionResults.notRecorded");
  const [filter, setFilter] = useState({ runId, extensionId: "", year: "", offset: 0 });
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ key: string; result?: ExtensionResults; error?: string }>();
  const [known, setKnown] = useState<{ key: string; capabilities: ExtensionResults["capabilities"] }>();
  const selection = filter.runId === runId ? filter : { runId, extensionId: "", year: "", offset: 0 };
  const { extensionId, year, offset } = selection;
  const runKey = JSON.stringify([runId]);
  const key = JSON.stringify([runKey, extensionId, year, LIMIT, offset, attempt]);
  const result = state?.key === key ? state.result : undefined;
  const error = state?.key === key ? state.error : undefined;
  const busy = Boolean(runId && state?.key !== key);
  const capabilities = known?.key === runKey ? known.capabilities : undefined;

  useEffect(() => {
    if (!runId) return;
    const abort = new AbortController();
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (extensionId) params.set("extension_id", extensionId);
    if (year) params.set("year", year);
    void (async () => {
      try {
        const response = await apiFetch(apiUrl(`runs/${encodeURIComponent(runId)}/extensions/artifacts?${params}`), { signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw new Error(record(body) && typeof body.error === "string" ? body.error : t("extensionResults.failed", { status: response.status }));
        if (!isExtensionResults(body)) throw new Error(t("extensionResults.schema"));
        if (body.run_id !== runId || body.scope.extension_id !== (extensionId || null) || body.scope.year !== (year ? Number(year) : null)
          || body.offset !== offset || body.limit !== LIMIT) throw new Error(t("extensionResults.scopeMismatch"));
        if (!abort.signal.aborted) { setState({ key, result: body }); setKnown({ key: runKey, capabilities: body.capabilities }); }
      } catch (caught) {
        if (!abort.signal.aborted) setState({ key, error: caught instanceof Error ? caught.message : t("extensionResults.cannotQuery") });
      }
    })();
    return () => abort.abort();
  }, [runId, extensionId, year, offset, key, runKey, t]);

  function change(next: { extensionId?: string; year?: string; offset?: number }) {
    setFilter({ ...selection, ...next, runId, offset: next.offset ?? 0 });
  }

  return <section className="panel extension-results-panel" aria-label={t("extensionResults.label")}>
    <header><small>{t("extensionResults.kicker")}</small><h3>{t("extensionResults.title")}</h3><p>{t("extensionResults.intro")}</p></header>
    {!runId ? <p className="extension-result-message">{t("extensionResults.selectRun")}</p> : <>
      <div className="extension-result-controls"><label>{t("extensionResults.extension")}<select aria-label={t("extensionResults.extensionLabel")} value={extensionId} disabled={!capabilities?.extensions.length} onChange={event => change({ extensionId: event.target.value })}><option value="">{t("extensionResults.allExtensions")}</option>{capabilities?.extensions.map(extension => <option key={extension.id} value={extension.id}>{extension.id} · {extension.version}</option>)}</select></label><label>{t("extensionResults.year")}<select aria-label={t("extensionResults.yearLabel")} value={year} disabled={!capabilities?.years.length} onChange={event => change({ year: event.target.value })}><option value="">{t("extensionResults.allYears")}</option>{capabilities?.years.map(value => <option key={value} value={value}>{value}</option>)}</select></label><button className="text-button" onClick={() => setAttempt(value => value + 1)} disabled={busy}>{t("extensionResults.reload")}</button></div>
      {busy && <p role="status" className="extension-result-message">{t("extensionResults.reading")}</p>}
      {error && <p role="alert" className="extension-result-message error">{error}</p>}
      {result?.reason_code === "no_extensions_selected" && <p role="status" className="extension-result-message">{result.message}</p>}
      {result && result.reason_code !== "no_extensions_selected" && <>
        <div className="extension-result-provenance"><span><small>{t("extensionResults.requested")}</small><code>{result.run_id}</code></span><span><small>{t("extensionResults.container")}</small><code>{text(result.identity.container_run_id)}</code></span><span><small>{t("extensionResults.moduleGraph")}</small><code>{text(result.identity.frozen_module_graph_sha256)}</code></span><span><small>{t("extensionResults.extensionGraph")}</small><code>{text(result.identity.frozen_extension_graph_sha256)}</code></span><span><small>{t("extensionResults.yearResults")}</small><code>{text(result.source.year_results.sha256)}</code></span><span><small>{t("extensionResults.resolution")}</small><code>{text(result.source.module_resolution.sha256)}</code></span></div>
        {result.status !== "available" && result.reason_code === "extensions_not_executed_in_scope" ? <p role="status" className="extension-result-message">{t("extensionResults.notExecuted", { message: result.message })}</p> : result.status !== "available" ? <p role="status" className={`extension-result-message ${result.status === "invalid" ? "error" : ""}`}>{t("extensionResults.status", { status: result.status, reason: result.reason_code ?? t("extensionResults.evidenceUnavailable"), message: result.message })}</p> : <>
          <div className="extension-result-items">{result.items.map((item, index) => <article key={`${item.extension_id}-${item.year}-${offset + index}`}><h4>{item.extension_id} · {item.extension_version} · {item.year}</h4><p>{t("extensionResults.namespace", { type: item.artifact_type, schema: item.schema_version, namespace: item.namespace })}</p><dl>{item.summary_fields.length ? item.summary_fields.map(field => <div key={field}><dt>{field}</dt><dd>{item.summary[field] == null ? t("extensionResults.fieldUnavailable") : String(item.summary[field])}</dd></div>) : <div><dt>{t("extensionResults.summaryFields")}</dt><dd>{t("extensionResults.noFields")}</dd></div>}</dl><details><summary>{t("extensionResults.identities")}</summary><div className="extension-result-provenance"><span><small>{t("extensionResults.manifest")}</small><code>{item.manifest_sha256}</code></span><span><small>{t("extensionResults.sourceInputs")}</small><code>{item.source_inputs_sha256}</code></span></div></details></article>)}</div>
          <div className="extension-result-page"><button className="text-button" disabled={busy || offset === 0} onClick={() => change({ offset: Math.max(0, offset - LIMIT) })}>{t("extensionResults.previous")}</button><span>{t("extensionResults.range", { first: result.items.length ? offset + 1 : 0, last: offset + result.count, total: result.total })}</span><button className="text-button" disabled={busy || !result.has_more} onClick={() => change({ offset: offset + LIMIT })}>{t("extensionResults.next")}</button></div>
        </>}
        <p className="extension-result-note">{t("extensionResults.scopeNote", { year: year || t("extensionResults.scopeAllYears"), extension: extensionId || t("extensionResults.scopeAllExtensions"), dimensions: result.capabilities.unavailable_dimensions.join(", ") })}</p>
      </>}
    </>}
  </section>;
}
