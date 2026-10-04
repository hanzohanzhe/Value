"use client";

export type TraceProfile = "off" | "summary" | "full";

const TRACE_LABELS: Record<TraceProfile, string> = {
  summary: "Summary",
  full: "Full market replay",
  off: "Advanced: Off",
};

export default function TraceCoverageNotice({
  traceLevel,
  bidReplayAvailable,
  onCreateFullReplayRevision,
}: {
  traceLevel: string;
  bidReplayAvailable: boolean;
  onCreateFullReplayRevision?: () => void;
}) {
  const profile = traceLevel in TRACE_LABELS ? traceLevel as TraceProfile : null;
  return <section className="trace-coverage-notice" aria-label="Recorded trace coverage">
    <header><span>Recorded trace</span><b>{profile ? TRACE_LABELS[profile] : traceLevel || "Not recorded"}</b></header>
    {profile === "summary" && !bidReplayAvailable && <div>
      <p><strong>Bid-level replay was not recorded.</strong> Dispatch, storage, curtailment, zonal flow and redispatch summaries remain available; missing bid detail is not zero.</p>
      {onCreateFullReplayRevision && <button className="secondary" onClick={onCreateFullReplayRevision}>Create a new Study revision with Full market replay</button>}
    </div>}
    {profile === "off" && <p>Optional period browsing was not recorded. Annual scientific results, integrity evidence and failure evidence remain available.</p>}
    {profile === "full" && <p>Summary science and the recorded bid, acceptance, settlement and solver detail are available through bounded views.</p>}
  </section>;
}
