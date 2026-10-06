"use client";

import { apiUrl } from "../shared/api";
import { useEffect, useRef, useState } from "react";
import { isCurtailmentQueryResponse, isRecord, type CurtailmentQueryResponse, type ResultResolution, type ResultSourceChoice } from "./result-query.types";
import { formatNumber } from "../shared/format.ts";
import { VALUE_STATES } from "../shared/valueStates.ts";
import { resultStatusView } from "../shared/reasonCodes.ts";
import { StatusPill } from "../shared/Callout";
import "./result-query.css";

const LIMIT = 48;
const format = (value: number | null | undefined) => formatNumber(value, 4) ?? VALUE_STATES.unavailable.text;
const identityText = (value: unknown) => typeof value === "string" && value ? value : "Not recorded";

/** G1-07: only an invalid result is an error; unavailable and withheld are explained, not alarmed. */
function StatusMessage({ status, reasonCode }: { status: string; reasonCode?: string | null }) {
  const view = resultStatusView(status, reasonCode);
  return <p role={view.isError ? "alert" : "status"} className={`result-query-message${view.isError ? " error" : ""}`}>
    <StatusPill tone={view.tone === "ok" ? "ok" : view.tone} title={reasonCode ?? undefined}>{view.label}</StatusPill>{" "}
    {view.message} Missing metrics are shown as unavailable, never as zero. <code>{reasonCode ?? "no_reason_recorded"}</code>
  </p>;
}

export default function ResultQueryPanel({ run }: { run?: { id: string; status: string } }) {
  const [source, setSource] = useState<ResultSourceChoice>("auto");
  const [resolution, setResolution] = useState<ResultResolution>("annual");
  const [yearInput, setYearInput] = useState("");
  const [fromInput, setFromInput] = useState("");
  const [toInput, setToInput] = useState("");
  const [window, setWindow] = useState({ year: "", from: "", to: "" });
  const [offset, setOffset] = useState(0);
  const [inputError, setInputError] = useState("");
  const [state, setState] = useState<{ key: string; report?: CurtailmentQueryResponse; error?: string }>();
  const [known, setKnown] = useState<{ key: string; capabilities: CurtailmentQueryResponse["capabilities"] }>();
  const generation = useRef(0);
  const contextKey = JSON.stringify([run?.id, source]);
  const requestKey = JSON.stringify([contextKey, resolution, window.year, window.from, window.to, offset, LIMIT]);
  const caps = known?.key === contextKey ? known.capabilities : undefined;
  const report = state?.key === requestKey ? state.report : undefined;
  const error = state?.key === requestKey ? state.error : undefined;
  const busy = Boolean(run && state?.key !== requestKey);
  const runId = run?.id;

  useEffect(() => {
    const attempt = ++generation.current;
    const abort = new AbortController();
    if (!runId) return () => abort.abort();
    const params = new URLSearchParams({ source, resolution, limit: String(LIMIT), offset: String(offset) });
    if (window.year) params.set("year", window.year);
    if (resolution === "half_hour") {
      if (window.from) params.set("period_from", window.from);
      if (window.to) params.set("period_to", window.to);
    }
    void (async () => {
      try {
        const response = await fetch(apiUrl(`runs/${encodeURIComponent(runId)}/results/vre-curtailment?${params}`), { signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw new Error(isRecord(body) && typeof body.error === "string" ? body.error : `Result query failed (${response.status})`);
        if (!isCurtailmentQueryResponse(body)) throw new Error("Result response does not match value.result-query/v1.");
        if (body.identity.run_id !== runId || body.identity.requested_run_id !== runId || body.source.requested !== source || body.scope.resolution !== resolution
          || body.scope.year !== (window.year ? Number(window.year) : null)
          || body.scope.period_from !== (resolution === "half_hour" && window.from ? Number(window.from) : null)
          || body.scope.period_to !== (resolution === "half_hour" && window.to ? Number(window.to) : null)
          || (source !== "auto" && body.source.kind !== source)
          || body.offset !== offset || body.limit !== LIMIT) throw new Error("Result identity or query scope does not match this selection.");
        if (!abort.signal.aborted && generation.current === attempt) {
          setState({ key: requestKey, report: body });
          setKnown({ key: contextKey, capabilities: body.capabilities });
        }
      } catch (caught) {
        if (!abort.signal.aborted && generation.current === attempt)
          setState({ key: requestKey, error: caught instanceof Error ? caught.message : "Cannot read results." });
      }
    })();
    return () => { abort.abort(); generation.current += 1; };
  }, [runId, source, resolution, window.year, window.from, window.to, offset, requestKey, contextKey]);

  function applyWindow() {
    if ([yearInput, fromInput, toInput].some(value => value && !/^\d+$/.test(value))
      || (yearInput && Number(yearInput) < 1)
      || (fromInput && toInput && Number(fromInput) > Number(toInput))) {
      setInputError("Use whole numbers and a period start no greater than the end."); return;
    }
    if (resolution === "half_hour" && !yearInput) { setInputError("Select a year before requesting half-hour periods."); return; }
    setInputError(""); setOffset(0);
    setWindow({ year: yearInput, from: resolution === "half_hour" ? fromInput : "", to: resolution === "half_hour" ? toInput : "" });
  }
  function changeSource(value: ResultSourceChoice) {
    setSource(value); setResolution("annual"); setWindow({ year: "", from: "", to: "" });
    setYearInput(""); setFromInput(""); setToInput(""); setOffset(0); setInputError("");
  }
  function changeResolution(value: ResultResolution) {
    setResolution(value); setOffset(0); setInputError("");
    setWindow({ year: value === "half_hour" ? yearInput : window.year, from: "", to: "" });
  }

  return <section className="panel result-query" aria-label="Versioned VRE result query">
    <header><div><small>Read-only result query · value.result-query/v1</small><h3>Final VRE curtailment · v2</h3></div><span>{run ? `Run ${run.id}` : "Select a Run"}</span></header>
    <p className="result-query-definition">Final curtailment is economic curtailment + forecast added − forecast avoided + redispatch added − redispatch avoided. Added and avoided energy remain separate; avoided energy is not additional curtailment. Rates use available VRE energy in the reported scope. Aggregation comes from the server.</p>
    {!run ? <p className="result-query-message">Choose a saved Run to inspect its recorded results.</p> : <>
      <div className="result-query-controls">
        <label>Result source<select aria-label="Result source" value={source} onChange={event => changeSource(event.target.value as ResultSourceChoice)}><option value="auto">Auto · recorded source</option><option value="sqlite">SQLite ledger</option><option value="compact">Compact result</option></select></label>
        <label>Result resolution<select aria-label="Result resolution" value={resolution} onChange={event => changeResolution(event.target.value as ResultResolution)}><option value="annual" disabled={Boolean(caps && !caps.available_resolutions.includes("annual"))}>Annual</option><option value="half_hour" disabled={!caps?.available_resolutions.includes("half_hour") || !yearInput}>Half hour · year required</option></select></label>
        <label>Result year<input aria-label="Result year" inputMode="numeric" placeholder="All years" value={yearInput} disabled={!caps?.available_dimensions.includes("year")} onChange={event => setYearInput(event.target.value)} /></label>
        {resolution === "half_hour" && <><label>Period from<input aria-label="Period from" inputMode="numeric" placeholder="First period" value={fromInput} disabled={!caps?.available_dimensions.includes("period_window")} onChange={event => setFromInput(event.target.value)} /></label><label>Period to<input aria-label="Period to" inputMode="numeric" placeholder="Last period" value={toInput} disabled={!caps?.available_dimensions.includes("period_window")} onChange={event => setToInput(event.target.value)} /></label></>}
        <button className="secondary" onClick={applyWindow} disabled={busy || !caps?.available_dimensions.includes("year")}>Apply result scope</button>
      </div>
      {inputError && <p role="alert" className="result-query-message error">{inputError}</p>}
      {busy && <p role="status" className="result-query-message">Reading this result scope…</p>}
      {error && <p role="alert" className="result-query-message error">{error}</p>}
      {report && <>
        <div className="result-query-provenance"><span><small>Source kind</small><b>{report.source.kind}</b></span><span><small>Source SHA-256</small><code>{identityText(report.source.artifact_sha256)}</code></span><span><small>Snapshot recorded by this Run</small><code>{identityText(report.identity.input_snapshot_id)}</code></span><span><small>Module graph SHA-256</small><code>{identityText(report.identity.module_resolution_graph_sha256)}</code></span><span><small>Run container</small><code>{report.identity.run_id}</code></span><span><small>Reported scope</small><code>{JSON.stringify(report.scope)}</code></span></div>
        {report.identity.missing_fields && report.identity.missing_fields.length > 0 && <p className="result-query-message">Some source identity fields were not recorded: {report.identity.missing_fields.join(", ")}. The enclosing Run record does not supply missing artifact provenance.</p>}
        {report.capabilities.unavailable_dimensions.length > 0 && <p className="result-query-message">Unavailable dimensions: {report.capabilities.unavailable_dimensions.join(", ")}. This source cannot reconstruct those dimensions.</p>}
        {report.status !== "reconciled" ? <StatusMessage status={report.status} reasonCode={report.reason_code} /> : <>
          <div className="result-query-table"><table><caption>{resolution === "annual" ? "Annual" : "Half-hour"} results · energy in MWh · {report.items.length} rows on this page</caption><thead><tr><th>Year{resolution === "half_hour" ? " / period" : ""}</th><th>Periods</th><th>Available VRE</th><th>Economic</th><th>Forecast added</th><th>Forecast avoided</th><th>Redispatch added</th><th>Redispatch avoided</th><th>Redispatch net</th><th>Final curtailment</th><th>Rate</th></tr></thead><tbody>{report.items.map(item => <tr key={`${item.year}-${item.period ?? "annual"}`}><td>{item.year}{resolution === "half_hour" ? ` / ${item.period}` : ""}</td><td>{item.period_count}</td><td>{format(item.available_mwh)}</td><td>{format(item.economic_mwh)}</td><td>{format(item.forecast_added_mwh)}</td><td>{format(item.forecast_avoided_mwh)}</td><td>{format(item.redispatch_added_mwh)}</td><td>{format(item.redispatch_avoided_mwh)}</td><td>{format(item.redispatch_net_mwh)}</td><td>{format(item.total_mwh)}</td><td>{item.rate == null ? "Unavailable" : `${format(item.rate * 100)}%`}</td></tr>)}</tbody></table></div>
          {!report.items.length && <p className="result-query-message">No rows match this scope.</p>}
          <div className="result-query-page"><button className="text-button" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>Previous result page</button><span>Rows {report.items.length ? offset + 1 : 0}–{offset + report.items.length} of {report.total}</span><button className="text-button" disabled={busy || !report.has_more} onClick={() => setOffset(offset + LIMIT)}>Next result page</button></div>
          <details><summary>Recorded source, reconciliation and period identities</summary><pre>{JSON.stringify({ source: report.source, identity: report.identity, periods: report.items.map(item => ({ year: item.year, period: item.period, period_id: item.period_id, identity_residual_mwh: item.identity_residual_mwh, aggregate_tolerance_mwh: item.aggregate_tolerance_mwh, realised_input_sha256: item.realised_input_sha256 })) }, null, 2)}</pre></details>
        </>}
      </>}
    </>}
  </section>;
}
