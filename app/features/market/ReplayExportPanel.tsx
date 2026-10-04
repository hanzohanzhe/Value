"use client";

import { useEffect, useState } from "react";

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

function absoluteJobUrl(apiOrigin: string, statusUrl: string): string {
  return new URL(statusUrl, apiOrigin).toString();
}

export default function ReplayExportPanel({
  apiOrigin,
  runId,
  years,
  selectedYear,
  selectedPeriod,
}: {
  apiOrigin: string;
  runId: string;
  years: number[];
  selectedYear?: number | null;
  selectedPeriod?: number | null;
}) {
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

  useEffect(() => {
    if (!job?.status_url || !["queued", "running"].includes(job.status)) return;
    let active = true;
    const timer = window.setInterval(() => {
      void fetch(absoluteJobUrl(apiOrigin, job.status_url as string), { cache: "no-store" })
        .then(async (response) => {
          const payload = await response.json() as ExportJobPayload;
          if (!response.ok) throw new Error(payload.error || "Replay export status unavailable");
          if (active) setJob((current) => current ? ({ ...payload, status_url: current?.status_url, request: current.request }) : current);
        })
        .catch((reason: Error) => { if (active) setError(reason.message); });
    }, 1500);
    return () => { active = false; window.clearInterval(timer); };
  }, [apiOrigin, job?.status, job?.status_url]);

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
      const response = await fetch(`${apiOrigin}/api/runs/${encodeURIComponent(runId)}/replay-exports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      });
      const payload = await response.json() as ExportJobPayload;
      if (!response.ok) throw new Error(payload.error || "Replay export could not start");
      setJob({ ...payload, request });
    } finally {
      setSubmitting(false);
    }
  }

  return <section className="panel replay-export-panel" aria-label="Replay export job">
    <div className="panel-head"><div><span>Background export</span><h3>Generate bounded replay evidence</h3></div>{job && <b>{job.status}</b>}</div>
    <p>Select one explicit range. Export generation runs independently of model execution and only this job is polled.</p>
    <div className="replay-export-controls">
      <label><span>Range</span><select value={rangeKind} disabled={controlsLocked} onChange={(event) => {
        const next = event.target.value as ExportRange;
        resetJobEvidence();
        setRangeKind(next);
        if (next === "complete") setOutputFormat("zip");
      }}><option value="">Choose a range</option><option value="period">Selected period</option><option value="24_hours">24 hours</option><option value="168_hours">168 hours</option><option value="year">Selected year</option><option value="complete">Complete run (ZIP only)</option></select></label>
      {rangeKind !== "complete" && <label><span>Year</span><select value={year} disabled={controlsLocked} onChange={(event) => { resetJobEvidence(); setYear(Number(event.target.value)); }}>{years.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>}
      {["period", "24_hours", "168_hours"].includes(rangeKind) && <label><span>First period</span><input type="number" min={0} value={periodFrom} disabled={controlsLocked} onChange={(event) => { resetJobEvidence(); setPeriodFrom(Math.max(0, Number(event.target.value))); }} /></label>}
      <label><span>Format</span><select value={rangeKind === "complete" ? "zip" : outputFormat} disabled={controlsLocked || rangeKind === "complete"} onChange={(event) => { resetJobEvidence(); setOutputFormat(event.target.value as ExportFormat); }}><option value="zip">Replay ZIP</option><option value="jsonl">Bounded JSONL</option><option value="csv">Bounded CSV</option></select></label>
      <button className="secondary" disabled={controlsLocked || !rangeKind} onClick={() => void startExport().catch((reason: Error) => setError(reason.message))}>Start export job</button>
    </div>
    {job && <div className="export-job-status" role="status"><span>Job <code>{job.job_id}</code></span><b>{job.status}</b>{job.status === "completed" && job.download_url && <a className="secondary" href={absoluteJobUrl(apiOrigin, job.download_url)}>Download completed artifact</a>}{job.status === "failed" && <small>{job.error || "Export failed"}</small>}</div>}
    {error && <div className="error-box" role="alert">{error}</div>}
  </section>;
}
