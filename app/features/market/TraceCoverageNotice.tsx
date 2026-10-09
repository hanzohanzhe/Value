"use client";

import { useT } from "../../i18n/LocaleProvider";
import type { MessageKey } from "../../i18n/index.ts";

export type TraceProfile = "off" | "summary" | "full";

// The labels are in app/i18n/messages/market.en.ts (trace.level.*).
const TRACE_LABELS: Record<TraceProfile, MessageKey> = {
  summary: "trace.level.summary",
  full: "trace.level.full",
  off: "trace.level.off",
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
  const t = useT();
  const profile = traceLevel in TRACE_LABELS ? traceLevel as TraceProfile : null;
  return <section className="trace-coverage-notice" aria-label={t("trace.label")}>
    <header><span>{t("trace.recorded")}</span><b>{profile ? t(TRACE_LABELS[profile]) : traceLevel || t("trace.notRecorded")}</b></header>
    {profile === "summary" && !bidReplayAvailable && <div>
      <p><strong>{t("trace.summary.lead")}</strong> {t("trace.summary.body")}</p>
      {onCreateFullReplayRevision && <button className="secondary" onClick={onCreateFullReplayRevision}>{t("trace.summary.createRevision")}</button>}
    </div>}
    {profile === "off" && <p>{t("trace.off.body")}</p>}
    {profile === "full" && <p>{t("trace.full.body")}</p>}
  </section>;
}
