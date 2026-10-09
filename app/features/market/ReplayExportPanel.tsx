"use client";

import { apiFetch, apiUrl } from "../../lib/api.ts";
import { createPoller } from "../../lib/poll.ts";
import { useEffect, useState } from "react";
import { replayExportNote } from "./replayExportNotes.ts";
import { useT } from "../../i18n/LocaleProvider";

type ExportRange = "" | "period" | "24_hours" | "168_hours" | "year" | "complete";
type ExportFormat = "zip" | "jsonl" | "csv";
type ExportRequest = {
  range_kind: Exclude<ExportRange, "">;
  year: number | null;
  period_from: number | null;
  period_to: number | null;
  output_format: ExportFormat;
};
type ExportJobPayload = {
  job_id: string;
  status: "queued" | "running" | "completed" | "failed";
  status_url?: string;
  download_url?: string;
  error?: string;
};
type ExportJob = ExportJobPayload & { request: ExportRequest };
/** The export job status read interval (unchanged from before R-9). */
const EXPORT_POLL_MS = 1500;

export default function ReplayExportPanel({
  runId,
  years,
  selectedYear,
  selectedPeriod,
}: {
  runId: string;
  years: number[];
  selectedYear?: number | null;
  selectedPeriod?: number | null;
}) {
  const t = useT();
  const initialYear = selectedYear ?? years[0] ?? 0;
  const [rangeKind, setRangeKind] = useState<ExportRange>("");
  const [year, setYear] = useState(initialYear);
  const [periodFrom, setPeriodFrom] = useState(selectedPeriod ?? 0);
  const [outputFormat, setOutputFormat] = useState<ExportFormat>("zip");
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const controlsLocked = submitting || Boolean(job && ["queued", "running"].includes(job.status));

  function resetJobEvidence() {
    setJob(null);
    setError("");
  }

  // R-9 (P1-polish, spec 4): the export job is followed by lib/poll.ts every
  // 1.5 s - one read at a time, paused while the page is hidden, read again at
  // once when it is shown; it stops when the job ends or the panel closes.
  const statusUrl = job?.status_url;
  const following = Boolean(statusUrl && job && ["queued", "running"].includes(job.status));
  useEffect(() => {
    if (!following || !statusUrl) return;
    const poller = createPoller<ExportJobPayload>({
      read: async (signal) => {
        const response = await apiFetch(statusUrl, { cache: "no-store", signal });
        const payload = await response.json() as ExportJobPayload;
        if (!response.ok) throw new Error(payload.error || t("export.statusUnavailable"));
        return payload;
      },
      onData: (payload) => setJob((current) => current ? ({ ...payload, status_url: current?.status_url, request: current.request }) : current),
      onError: (reason) => setError(reason instanceof Error ? reason.message : String(reason)),
      interval: () => EXPORT_POLL_MS,
    });
    poller.start();
    return () => poller.stop();
  }, [following, statusUrl, t]);

  async function startExport() {
    if (!rangeKind || controlsLocked) return;
    setError("");
    setJob(null);
    const lengths: Partial<Record<ExportRange, number>> = { period: 1, "24_hours": 48, "168_hours": 336 };
    const length = lengths[rangeKind];
    const request: ExportRequest = {
      range_kind: rangeKind,
      year: rangeKind === "complete" ? null : year,
      period_from: length ? periodFrom : null,
      period_to: length ? periodFrom + length - 1 : null,
      output_format: rangeKind === "complete" ? "zip" : outputFormat,
    };
    setSubmitting(true);
    try {
      const response = await apiFetch(apiUrl(`runs/${encodeURIComponent(runId)}/replay-exports`), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const payload = await response.json() as ExportJobPayload;
      if (!response.ok) throw new Error(payload.error || t("export.couldNotStart"));
      setJob({ ...payload, request });
    } finally {
      setSubmitting(false);
    }
  }

  return <section className="panel replay-export-panel" aria-label={t("export.label")}>
    <div className="panel-head"><div><span>{t("export.kicker")}</span><h3>{t("export.title")}</h3></div>{job && <b>{job.status}</b>}</div>
    <p>{t("export.intro")}</p>
    <div className="replay-export-controls">
      <label><span>{t("export.range")}</span><select value={rangeKind} disabled={controlsLocked} onChange={(event) => {
        const next = event.target.value as ExportRange;
        resetJobEvidence();
        setRangeKind(next);
        if (next === "complete") setOutputFormat("zip");
      }}><option value="">{t("export.range.choose")}</option><option value="period">{t("export.range.period")}</option><option value="24_hours">{t("export.range.hours24")}</option><option value="168_hours">{t("export.range.hours168")}</option><option value="year">{t("export.range.year")}</option><option value="complete">{t("export.range.complete")}</option></select></label>
      {rangeKind !== "complete" && <label><span>{t("export.year")}</span><select value={year} disabled={controlsLocked} onChange={(event) => { resetJobEvidence(); setYear(Number(event.target.value)); }}>{years.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>}
      {["period", "24_hours", "168_hours"].includes(rangeKind) && <label><span>{t("export.firstPeriod")}</span><input type="number" min={0} value={periodFrom} disabled={controlsLocked} onChange={(event) => { resetJobEvidence(); setPeriodFrom(Math.max(0, Number(event.target.value))); }} /></label>}
      <label><span>{t("export.format")}</span><select value={rangeKind === "complete" ? "zip" : outputFormat} disabled={controlsLocked || rangeKind === "complete"} onChange={(event) => { resetJobEvidence(); setOutputFormat(event.target.value as ExportFormat); }}><option value="zip">{t("export.format.zip")}</option><option value="jsonl">{t("export.format.jsonl")}</option><option value="csv">{t("export.format.csv")}</option></select></label>
      <button className="secondary" disabled={controlsLocked || !rangeKind} onClick={() => void startExport().catch((reason: Error) => setError(reason.message))}>{t("export.start")}</button>
    </div>
    {replayExportNote(rangeKind === "complete" ? "zip" : outputFormat) && <small className="replay-export-note value-new-control">{replayExportNote(rangeKind === "complete" ? "zip" : outputFormat)}</small>}
    {job && <div className="export-job-status" role="status"><span>{t("export.job")} <code>{job.job_id}</code></span><b>{job.status}</b>{job.status === "completed" && job.download_url && <a className="secondary" href={job.download_url}>{t("export.download")}</a>}{job.status === "failed" && <small>{job.error || t("export.failed")}</small>}</div>}
    {error && <div className="error-box" role="alert">{error}</div>}
  </section>;
}
