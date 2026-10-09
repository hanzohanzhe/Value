"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { useEffect, useRef, useState } from "react";
import { isCurtailmentQueryResponse, isRecord, type CurtailmentQueryResponse, type ResultResolution, type ResultSourceChoice } from "./result-query.types";
import { formatNumber } from "../shared/format.ts";
import { valueStateText } from "../shared/valueStates.ts";
import { resultStatusView } from "../shared/reasonCodes.ts";
import { StatusPill } from "../shared/Callout";
import "./result-query.css";
import { useT } from "../../i18n/LocaleProvider";

const LIMIT = 48;
const format = (value: number | null | undefined) => formatNumber(value, 4) ?? valueStateText("unavailable");

/** G1-07: only an invalid result is an error; unavailable and withheld are explained, not alarmed. */
function StatusMessage({ status, reasonCode, coveragePercent }: { status: string; reasonCode?: string | null; coveragePercent?: number | null }) {
  const t = useT();
  const view = resultStatusView(status, reasonCode, coveragePercent);
  return <p role={view.isError ? "alert" : "status"} className={`result-query-message${view.isError ? " error" : ""}`}>
    <StatusPill tone={view.tone === "ok" ? "ok" : view.tone} title={reasonCode ?? undefined}>{view.label}</StatusPill>{" "}
    {view.message} {t("resultQuery.missingNote")} <code>{reasonCode ?? "no_reason_recorded"}</code>
  </p>;
}

export default function ResultQueryPanel({ run }: { run?: { id: string; status: string } }) {
  const t = useT();
  const identityText = (value: unknown) => typeof value === "string" && value ? value : t("resultQuery.notRecorded");
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
        const response = await apiFetch(apiUrl(`runs/${encodeURIComponent(runId)}/results/vre-curtailment?${params}`), { signal: abort.signal, cache: "no-store" });
        const body: unknown = await response.json();
        if (!response.ok) throw new Error(isRecord(body) && typeof body.error === "string" ? body.error : t("resultQuery.failed", { status: response.status }));
        if (!isCurtailmentQueryResponse(body)) throw new Error(t("resultQuery.schema"));
        if (body.identity.run_id !== runId || body.identity.requested_run_id !== runId || body.source.requested !== source || body.scope.resolution !== resolution
          || body.scope.year !== (window.year ? Number(window.year) : null)
          || body.scope.period_from !== (resolution === "half_hour" && window.from ? Number(window.from) : null)
          || body.scope.period_to !== (resolution === "half_hour" && window.to ? Number(window.to) : null)
          || (source !== "auto" && body.source.kind !== source)
          || body.offset !== offset || body.limit !== LIMIT) throw new Error(t("resultQuery.scopeMismatch"));
        if (!abort.signal.aborted && generation.current === attempt) {
          setState({ key: requestKey, report: body });
          setKnown({ key: contextKey, capabilities: body.capabilities });
        }
      } catch (caught) {
        if (!abort.signal.aborted && generation.current === attempt)
          setState({ key: requestKey, error: caught instanceof Error ? caught.message : t("resultQuery.cannotRead") });
      }
    })();
    return () => { abort.abort(); generation.current += 1; };
  }, [runId, source, resolution, window.year, window.from, window.to, offset, requestKey, contextKey, t]);

  function applyWindow() {
    if ([yearInput, fromInput, toInput].some(value => value && !/^\d+$/.test(value))
      || (yearInput && Number(yearInput) < 1)
      || (fromInput && toInput && Number(fromInput) > Number(toInput))) {
      setInputError(t("resultQuery.wholeNumbers")); return;
    }
    if (resolution === "half_hour" && !yearInput) { setInputError(t("resultQuery.yearFirst")); return; }
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

  return <section className="panel result-query" aria-label={t("resultQuery.label")}>
    <header><div><small>{t("resultQuery.kicker")}</small><h2>{t("resultQuery.title")}</h2></div><span>{run ? t("resultQuery.run", { run: run.id }) : t("resultQuery.selectRun")}</span></header>
    <p className="result-query-definition">{t("resultQuery.definition")}</p>
    {!run ? <p className="result-query-message">{t("resultQuery.chooseRun")}</p> : <>
      <div className="result-query-controls">
        <label>{t("resultQuery.source")}<select aria-label={t("resultQuery.source")} value={source} onChange={event => changeSource(event.target.value as ResultSourceChoice)}><option value="auto">{t("resultQuery.source.auto")}</option><option value="sqlite">{t("resultQuery.source.sqlite")}</option><option value="compact">{t("resultQuery.source.compact")}</option></select></label>
        <label>{t("resultQuery.resolution")}<select aria-label={t("resultQuery.resolution")} value={resolution} onChange={event => changeResolution(event.target.value as ResultResolution)}><option value="annual" disabled={Boolean(caps && !caps.available_resolutions.includes("annual"))}>{t("resultQuery.resolution.annual")}</option><option value="half_hour" disabled={!caps?.available_resolutions.includes("half_hour") || !yearInput}>{t("resultQuery.resolution.halfHour")}</option></select></label>
        <label>{t("resultQuery.year")}<input aria-label={t("resultQuery.year")} inputMode="numeric" placeholder={t("resultQuery.year.placeholder")} value={yearInput} disabled={!caps?.available_dimensions.includes("year")} onChange={event => setYearInput(event.target.value)} /></label>
        {resolution === "half_hour" && <><label>{t("resultQuery.from")}<input aria-label={t("resultQuery.from")} inputMode="numeric" placeholder={t("resultQuery.from.placeholder")} value={fromInput} disabled={!caps?.available_dimensions.includes("period_window")} onChange={event => setFromInput(event.target.value)} /></label><label>{t("resultQuery.to")}<input aria-label={t("resultQuery.to")} inputMode="numeric" placeholder={t("resultQuery.to.placeholder")} value={toInput} disabled={!caps?.available_dimensions.includes("period_window")} onChange={event => setToInput(event.target.value)} /></label></>}
        <button className="secondary" onClick={applyWindow} disabled={busy || !caps?.available_dimensions.includes("year")}>{t("resultQuery.apply")}</button>
      </div>
      {inputError && <p role="alert" className="result-query-message error">{inputError}</p>}
      {busy && <p role="status" className="result-query-message">{t("resultQuery.reading")}</p>}
      {error && <p role="alert" className="result-query-message error">{error}</p>}
      {report && <>
        {/* R5 R-低7: an unavailable result has no source artifact to identify; only its reason is shown. */}
        {report.status !== "unavailable" && resultStatusView(report.status, report.reason_code).state !== "in_progress" && <><div className="result-query-provenance"><span><small>{t("resultQuery.sourceKind")}</small><b>{report.source.kind}</b></span><span><small>{t("resultQuery.sourceSha")}</small><code>{identityText(report.source.artifact_sha256)}</code></span><span><small>{t("resultQuery.snapshot")}</small><code>{identityText(report.identity.input_snapshot_id)}</code></span><span><small>{t("resultQuery.graph")}</small><code>{identityText(report.identity.module_resolution_graph_sha256)}</code></span><span><small>{t("resultQuery.container")}</small><code>{report.identity.run_id}</code></span><span><small>{t("resultQuery.scope")}</small><code>{JSON.stringify(report.scope)}</code></span></div>
        {report.identity.missing_fields && report.identity.missing_fields.length > 0 && <p className="result-query-message">{t("resultQuery.missingFields", { fields: report.identity.missing_fields.join(", ") })}</p>}</>}
        {report.capabilities.unavailable_dimensions.length > 0 && <p className="result-query-message">{t("resultQuery.unavailableDimensions", { dimensions: report.capabilities.unavailable_dimensions.join(", ") })}</p>}
        {report.status !== "reconciled" ? <StatusMessage status={report.status} reasonCode={report.reason_code} coveragePercent={report.coverage?.coverage_percent} /> : <>
          <div className="result-query-table"><table><caption>{t(resolution === "annual" ? "resultQuery.caption.annual" : "resultQuery.caption.halfHour", { count: report.items.length })}</caption><thead><tr><th>{t(resolution === "half_hour" ? "resultQuery.col.yearPeriod" : "resultQuery.col.year")}</th><th>{t("resultQuery.col.periods")}</th><th>{t("resultQuery.col.available")}</th><th>{t("resultQuery.col.economic")}</th><th>{t("resultQuery.col.forecastAdded")}</th><th>{t("resultQuery.col.forecastAvoided")}</th><th>{t("resultQuery.col.redispatchAdded")}</th><th>{t("resultQuery.col.redispatchAvoided")}</th><th>{t("resultQuery.col.redispatchNet")}</th><th>{t("resultQuery.col.final")}</th><th>{t("resultQuery.col.rate")}</th></tr></thead><tbody>{report.items.map(item => <tr key={`${item.year}-${item.period ?? "annual"}`}><td>{item.year}{resolution === "half_hour" ? ` / ${item.period}` : ""}</td><td>{item.period_count}</td><td>{format(item.available_mwh)}</td><td>{format(item.economic_mwh)}</td><td>{format(item.forecast_added_mwh)}</td><td>{format(item.forecast_avoided_mwh)}</td><td>{format(item.redispatch_added_mwh)}</td><td>{format(item.redispatch_avoided_mwh)}</td><td>{format(item.redispatch_net_mwh)}</td><td>{format(item.total_mwh)}</td><td>{item.rate == null ? t("resultQuery.unavailable") : `${format(item.rate * 100)}%`}</td></tr>)}</tbody></table></div>
          {!report.items.length && <p className="result-query-message">{t("resultQuery.noRows")}</p>}
          <div className="result-query-page"><button className="text-button" disabled={busy || offset === 0} onClick={() => setOffset(Math.max(0, offset - LIMIT))}>{t("resultQuery.previous")}</button><span>{t("resultQuery.rows", { first: report.items.length ? offset + 1 : 0, last: offset + report.items.length, total: report.total })}</span><button className="text-button" disabled={busy || !report.has_more} onClick={() => setOffset(offset + LIMIT)}>{t("resultQuery.next")}</button></div>
          <details><summary>{t("resultQuery.details")}</summary><pre>{JSON.stringify({ source: report.source, identity: report.identity, periods: report.items.map(item => ({ year: item.year, period: item.period, period_id: item.period_id, identity_residual_mwh: item.identity_residual_mwh, aggregate_tolerance_mwh: item.aggregate_tolerance_mwh, realised_input_sha256: item.realised_input_sha256 })) }, null, 2)}</pre></details>
        </>}
      </>}
    </>}
  </section>;
}
