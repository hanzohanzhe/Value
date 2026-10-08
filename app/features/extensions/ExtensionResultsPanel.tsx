"use client";

import { apiUrl } from "../shared/api";
import { useEffect, useState } from "react";
import { isExtensionResults, record, type ExtensionResults } from "./extension-results.types";
import "./ExtensionResultsPanel.css";

const LIMIT = 20;
const text = (value: string | null) => value ?? "Not recorded";

export default function ExtensionResultsPanel({ runId }: { runId?: string }) {
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
        const response = await fetch(apiUrl(`runs/${encodeURIComponent(runId)}/extensions/artifacts?${params}`), { signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw new Error(record(body) && typeof body.error === "string" ? body.error : `Extension results failed (${response.status})`);
        if (!isExtensionResults(body)) throw new Error("Extension result response does not match value.extension-results/v1.");
        if (body.run_id !== runId || body.scope.extension_id !== (extensionId || null) || body.scope.year !== (year ? Number(year) : null)
          || body.offset !== offset || body.limit !== LIMIT) throw new Error("The result identity or scope does not match this selection.");
        if (!abort.signal.aborted) { setState({ key, result: body }); setKnown({ key: runKey, capabilities: body.capabilities }); }
      } catch (caught) {
        if (!abort.signal.aborted) setState({ key, error: caught instanceof Error ? caught.message : "Cannot query extension results." });
      }
    })();
    return () => abort.abort();
  }, [runId, extensionId, year, offset, key, runKey]);

  function change(next: { extensionId?: string; year?: string; offset?: number }) {
    setFilter({ ...selection, ...next, runId, offset: next.offset ?? 0 });
  }

  return <section className="panel extension-results-panel" aria-label="Frozen extension results">
    <header><small>Historical extension evidence · value.extension-results/v1</small><h3>Extension artifact summaries</h3><p>These summaries use the declarations and hook source identities frozen in this Run. Only declared scalar summary fields are shown. Querying results does not execute extension code or consult the current registry.</p></header>
    {!runId ? <p className="extension-result-message">Select a Run to inspect its recorded extension artifacts.</p> : <>
      <div className="extension-result-controls"><label>Frozen extension<select aria-label="Result extension" value={extensionId} disabled={!capabilities?.extensions.length} onChange={event => change({ extensionId: event.target.value })}><option value="">All frozen extensions</option>{capabilities?.extensions.map(extension => <option key={extension.id} value={extension.id}>{extension.id} · {extension.version}</option>)}</select></label><label>Recorded year<select aria-label="Extension result year" value={year} disabled={!capabilities?.years.length} onChange={event => change({ year: event.target.value })}><option value="">All recorded years</option>{capabilities?.years.map(value => <option key={value} value={value}>{value}</option>)}</select></label><button className="text-button" onClick={() => setAttempt(value => value + 1)} disabled={busy}>Reload extension evidence</button></div>
      {busy && <p role="status" className="extension-result-message">Reading this Run and extension scope…</p>}
      {error && <p role="alert" className="extension-result-message error">{error}</p>}
      {result?.reason_code === "no_extensions_selected" && <p role="status" className="extension-result-message">{result.message}</p>}
      {result && result.reason_code !== "no_extensions_selected" && <>
        <div className="extension-result-provenance"><span><small>Requested Run</small><code>{result.run_id}</code></span><span><small>Container Run identity</small><code>{text(result.identity.container_run_id)}</code></span><span><small>Frozen module graph</small><code>{text(result.identity.frozen_module_graph_sha256)}</code></span><span><small>Frozen extension graph</small><code>{text(result.identity.frozen_extension_graph_sha256)}</code></span><span><small>Year-results SHA-256</small><code>{text(result.source.year_results.sha256)}</code></span><span><small>Frozen-resolution SHA-256</small><code>{text(result.source.module_resolution.sha256)}</code></span></div>
        {result.status !== "available" && result.reason_code === "extensions_not_executed_in_scope" ? <p role="status" className="extension-result-message">Extensions did not run in this scope. {result.message}</p> : result.status !== "available" ? <p role="status" className={`extension-result-message ${result.status === "invalid" ? "error" : ""}`}>Extension results {result.status}: {result.reason_code ?? "Evidence unavailable"}. {result.message}</p> : <>
          <div className="extension-result-items">{result.items.map((item, index) => <article key={`${item.extension_id}-${item.year}-${offset + index}`}><h4>{item.extension_id} · {item.extension_version} · {item.year}</h4><p>{item.artifact_type} · {item.schema_version} · namespace {item.namespace}</p><dl>{item.summary_fields.length ? item.summary_fields.map(field => <div key={field}><dt>{field}</dt><dd>{item.summary[field] == null ? "Unavailable · missing, nested or outside the summary bound" : String(item.summary[field])}</dd></div>) : <div><dt>Summary fields</dt><dd>None declared by the frozen manifest</dd></div>}</dl><details><summary>Artifact identities</summary><div className="extension-result-provenance"><span><small>Manifest SHA-256</small><code>{item.manifest_sha256}</code></span><span><small>Recorded source inputs SHA-256</small><code>{item.source_inputs_sha256}</code></span></div></details></article>)}</div>
          <div className="extension-result-page"><button className="text-button" disabled={busy || offset === 0} onClick={() => change({ offset: Math.max(0, offset - LIMIT) })}>Previous extension page</button><span>Artifacts {result.items.length ? offset + 1 : 0}–{offset + result.count} of {result.total}</span><button className="text-button" disabled={busy || !result.has_more} onClick={() => change({ offset: offset + LIMIT })}>Next extension page</button></div>
        </>}
        <p className="extension-result-note">Recorded scope: {year || "all recorded years"} · {extensionId || "all frozen extensions"}. Unavailable dimensions: {result.capabilities.unavailable_dimensions.join(", ")}. An audit artifact is evidence of its declared hook output; it is not scientific validation of a new physical method.</p>
      </>}
    </>}
  </section>;
}
