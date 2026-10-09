"use client";

// Spec 4.4 (decision A2): the full-year list of stress events, paged 50 at a
// time in start-period order, each with a Replay jump. Shown in Market replay
// for every Run whose ledger records stress events; "Show stress events" on
// the Run context bar opens it.
import { useEffect, useRef, useState } from "react";
import { getJson, apiUrl } from "../../lib/api.ts";
import type { ResultCoverage } from "../shared/coverageView.ts";
import { useT } from "../../i18n/LocaleProvider";
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
  const t = useT();
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
        if (!isStressEventPage(page)) setLoad({ key, status: "error", error: t("stress.list.notPage") });
        else setLoad({ key, status: "success", page });
      })
      .catch((reason: unknown) => { if (!controller.signal.aborted) setLoad({ key, status: "error", error: reason instanceof Error ? reason.message : t("stress.list.unavailable") }); });
    return () => controller.abort();
  }, [key, offset, runId, t, year]);
  const current = load?.key === key ? load : { key, status: "loading" as const };
  const page = current.status === "success" ? current.page : undefined;
  useEffect(() => {
    if (!focus || !page) return;
    section.current?.scrollIntoView?.({ block: "start" });
    section.current?.focus({ preventScroll: true });
    onFocused?.();
  }, [focus, onFocused, page]);
  const summary = stressEventSummary(page);
  return <section ref={section} id="stress-events" className="panel evidence-panel stress-event-list value-new-control" aria-label={t("stress.list.label")} tabIndex={-1}>
    <div className="panel-head"><div><span>{t("stress.list.kicker")}</span><h3>{stressEventHeading(coverage, year)}</h3></div><strong>{summary}</strong></div>
    <p className="stress-event-note">{t("stress.list.note")}</p>
    {current.status === "loading" ? <p className="loading">{t("stress.list.loading")}</p>
      : current.status === "error" ? <div className="error-box">{current.error}</div>
      : page && page.items.length ? <>
        <div className="table-scroll"><table><thead><tr><th>{t("stress.col.start")}</th><th>{t("stress.col.periods")}</th><th>{t("stress.col.shortfall")}</th><th>{t("stress.col.type")}</th><th><span className="visually-hidden">{t("stress.col.replay")}</span></th></tr></thead>
          <tbody>{page.items.map((event) => { const row = stressEventRow(event, page.period_hours); return <tr key={row.key}><td><b>{row.start}</b><small>{t("stress.list.period", { period: row.startPeriod })}</small></td><td>{row.periods}</td><td>{row.shortfall ?? t("stress.list.notRecorded")}</td><td>{row.type}</td><td><button type="button" className="text-button" onClick={() => onReplay(event.year, row.replayFrom, event.start_period)} aria-label={t("stress.list.replayLabel", { period: event.start_period })}>{t("stress.list.replay")}</button></td></tr>; })}</tbody></table></div>
        <div className="bounded-page-controls"><button type="button" className="text-button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - page.limit))}>{t("stress.list.previous")}</button><span>{t("stress.list.range", { first: offset + 1, last: offset + page.items.length, total: page.total })}</span><button type="button" className="text-button" disabled={!page.has_more} onClick={() => setOffset(offset + page.limit)}>{t("stress.list.next")}</button></div>
      </> : page ? <p className="stress-event-note">{stressEventEmptyText(page, coverage, year, computedPeriods)}</p> : null}
  </section>;
}
