"use client";

// Spec 4.4 (decision A2): the full-year list of stress events, paged 50 at a
// time in start-period order, each with a Replay jump. Shown in Market replay
// for every Run whose ledger records stress events; "Show stress events" on
// the Run context bar opens it.
import { useEffect, useRef, useState } from "react";
import { getJson, apiUrl } from "../shared/api";
import type { ResultCoverage } from "../shared/coverageView.ts";
import { isStressEventPage, stressEventEmptyText, stressEventHeading, stressEventQuery, stressEventRow, stressEventSummary, type StressEventPage } from "./stressEventsView.ts";

type Load = { key: string; status: "loading" | "success" | "error"; page?: StressEventPage; error?: string };

export default function StressEventList({ runId, year, coverage, computedPeriods, onReplay, focus, onFocused }: {
  runId: string; year: number; coverage?: ResultCoverage | null;
  /** Periods a non-annual Run computed (R-D3), when its record says. */
  computedPeriods?: number | null;
  onReplay: (year: number, periodFrom: number, period: number) => void;
  /** Scroll the list into view once loaded ("Show stress events"). */
  focus?: boolean;
  onFocused?: () => void;
}) {
  const [offset, setOffset] = useState(0);
  const key = JSON.stringify([runId, year, offset]);
  const [load, setLoad] = useState<Load | null>(null);
  const section = useRef<HTMLElement | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    void getJson<StressEventPage>(apiUrl(`runs/${runId}/market/stress-events?${stressEventQuery(year, offset)}`), controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        // An unexpected body (an older or foreign backend) is an error, never an empty list.
        if (!isStressEventPage(page)) setLoad({ key, status: "error", error: "Stress events unavailable: the service did not return a stress-event page." });
        else setLoad({ key, status: "success", page });
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setLoad({ key, status: "error", error: reason instanceof Error ? reason.message : "Stress events unavailable" }); });
    return () => controller.abort();
  }, [key, offset, runId, year]);
  const current = load?.key === key ? load : { key, status: "loading" as const };
  const page = current.status === "success" ? current.page : undefined;
  useEffect(() => {
    if (!focus || !page) return;
    section.current?.scrollIntoView?.({ block: "start" });
    section.current?.focus({ preventScroll: true });
    onFocused?.();
  }, [focus, onFocused, page]);
  const summary = stressEventSummary(page);
  return <section ref={section} id="stress-events" className="panel evidence-panel stress-event-list value-new-control" aria-label="Stress events" tabIndex={-1}>
    <div className="panel-head"><div><span>Supply below demand (decision A2)</span><h3>{stressEventHeading(coverage, year)}</h3></div><strong>{summary}</strong></div>
    <p className="stress-event-note">Periods in which accepted supply fell short of demand. Dispatch was not altered; each shortfall is recorded as unserved energy.</p>
    {current.status === "loading" ? <p className="loading">Loading stress events…</p>
      : current.status === "error" ? <div className="error-box">{current.error}</div>
      : page && page.items.length ? <>
        <div className="table-scroll"><table><thead><tr><th>Start (model date &amp; time, UTC)</th><th>Periods</th><th>Shortfall</th><th>Type</th><th><span className="visually-hidden">Replay</span></th></tr></thead>
          <tbody>{page.items.map((event) => { const row = stressEventRow(event, page.period_hours); return <tr key={row.key}><td><b>{row.start}</b><small>period {row.startPeriod}</small></td><td>{row.periods}</td><td>{row.shortfall ?? "Not recorded"}</td><td>{row.type}</td><td><button type="button" className="text-button" onClick={() => onReplay(event.year, row.replayFrom, event.start_period)} aria-label={`Replay the stress event starting at period ${event.start_period}`}>Replay →</button></td></tr>; })}</tbody></table></div>
        <div className="bounded-page-controls"><button type="button" className="text-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - page.limit))}>Previous events</button><span>Events {offset + 1}–{offset + page.items.length} of {page.total}</span><button type="button" className="text-button" disabled={!page.has_more} onClick={() => setOffset(offset + page.limit)}>Next events</button></div>
      </> : page ? <p className="stress-event-note">{stressEventEmptyText(page, coverage, year, computedPeriods)}</p> : null}
  </section>;
}
