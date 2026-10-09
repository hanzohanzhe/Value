"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import "./data-workbench.css";
import { DataWorkbenchClient } from "./client";
import { BuildBenchmark } from "./BuildBenchmark";
import { CandidateReview } from "./CandidateReview";
import { OverlayEditor } from "./OverlayEditor";
import { InstalledPacks } from "./InstalledPacks";
import { OfficialSources } from "./OfficialSources";
import { MAX_POLL_FAILURES, browserStorage, elapsedSeconds, isActiveJob, pollDelay, progressPercent, readTrackedJob, writeTrackedJob } from "./jobTracking.ts";
import { Button, Tabs, useSearchParamState } from "../../ui";
import { createPoller } from "../../lib/poll.ts";
import { useT } from "../../i18n/LocaleProvider";
import { messageOf, showMessage, type LocalizedMessage } from "../shared/localizedMessage.ts";
import type {
  CandidateReview as CandidateReviewRecord,
  CandidateSummary,
  DataJob,
  DataSourceDefinition,
  InstalledBundle,
  SourceRevision,
  ValidationReport,
} from "./types";

// P1 W4b (spec 2, 3, 6.3): WAI-ARIA tabs whose current tab is in the URL
// (?workbench=), wording from the dictionaries (dataWorkbench.*), and F4-05:
// a job keeps being followed through transient errors (back-off, then a
// "Check the job again" button), shows its progress and elapsed time, can be
// cancelled with a visible outcome, blocks a second job, and is picked up
// again after a reload (jobTracking.ts).
const TABS = ["installed", "overlays", "sources", "build", "candidates"] as const;
type Tab = (typeof TABS)[number];
const TAB_LABELS = {
  installed: "dataWorkbench.tab.installed", overlays: "dataWorkbench.tab.overlays", sources: "dataWorkbench.tab.sources",
  build: "dataWorkbench.tab.build", candidates: "dataWorkbench.tab.candidates",
} as const;
const acceptedRights = new Set(["redistributable", "pointer_only", "local_use_only"]);

export default function DataWorkbench({ onWorkspaceChanged }: { onWorkspaceChanged?: () => Promise<void> | void }) {
  const t = useT();
  const client = useMemo(() => new DataWorkbenchClient(), []);
  const [tabValue, setTab] = useSearchParamState("workbench", "installed", TABS);
  const tab = tabValue as Tab;
  const [sources, setSources] = useState<DataSourceDefinition[]>([]);
  const [revisions, setRevisions] = useState<SourceRevision[]>([]);
  const [candidates, setCandidates] = useState<CandidateSummary[]>([]);
  const [bundles, setBundles] = useState<InstalledBundle[]>([]);
  const [job, setJob] = useState<DataJob | null>(null);
  const [resumed, setResumed] = useState(false);
  const [failures, setFailures] = useState<{ count: number; error: string }>({ count: 0, error: "" });
  const [now, setNow] = useState(0);
  const [cancelError, setCancelError] = useState("");
  const [selected, setSelected] = useState<CandidateSummary | null>(null);
  const [validation, setValidation] = useState<ValidationReport | null>(null);
  const [review, setReview] = useState<CandidateReviewRecord | null>(null);
  const [version, setVersion] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [accepted, setAccepted] = useState<string[]>([]);
  const [message, setMessage] = useState<LocalizedMessage | null>(null);
  const active = isActiveJob(job);
  const lost = failures.count >= MAX_POLL_FAILURES;

  const refresh = useCallback(async () => {
    try {
      const [sourceData, revisionData, candidateData, bundleData] = await Promise.all([
        client.sources(), client.revisions(), client.candidates(), client.bundles(),
      ]);
      setSources(sourceData.sources);
      setRevisions(revisionData.revisions);
      setCandidates(candidateData.candidates.filter((item) => !item.directory_id.startsWith("overlay-")));
      setBundles(bundleData.bundles);
    } catch (error) {
      setMessage(messageOf(error, "dataWorkbench.error.service"));
    }
  }, [client]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refresh();
      // F4-05: pick up the job this browser started before a reload.
      const tracked = readTrackedJob(browserStorage());
      if (!tracked) return;
      client.job(tracked).then((response) => {
        if (isActiveJob(response.job)) { setJob(response.job); setResumed(true); setNow(Date.now()); }
        else writeTrackedJob(browserStorage(), null);
      }).catch(() => writeTrackedJob(browserStorage(), null));
    }, 0);
    return () => window.clearTimeout(timer);
  }, [client, refresh]);

  // R-9 (P1-polish, spec 4): the job is followed by lib/poll.ts with the
  // job's own cadence (jobTracking.pollDelay) - one read at a time, paused
  // while the page is hidden, read again at once when it is shown; after
  // MAX_POLL_FAILURES failures in a row it stops ("Check the job again").
  const jobId = job?.job_id ?? "";
  const following = Boolean(jobId) && active && !lost;
  useEffect(() => {
    if (!following) return;
    const poller = createPoller({
      read: () => client.job(jobId),
      onData: (response) => {
        setJob(response.job); setFailures({ count: 0, error: "" }); setNow(Date.now());
        if (!isActiveJob(response.job)) {
          writeTrackedJob(browserStorage(), null);
          if (response.job.status === "completed") void refresh();
        }
      },
      onError: (error, count) => {
        setFailures({ count, error: showMessage(t, messageOf(error, "dataWorkbench.error.polling")) });
        if (count >= MAX_POLL_FAILURES) poller.stop();
      },
      interval: pollDelay,
    });
    poller.start();
    return () => poller.stop();
  }, [client, following, jobId, refresh, t]);

  const currentRevision = (sourceId: string) => revisions
    .filter((item) => item.source_id === sourceId && item.status !== "superseded")
    .sort((left, right) => right.publication_date.localeCompare(left.publication_date))[0];
  const pinnedSources = sources.filter((source) => Boolean(currentRevision(source.source_id)?.object_key));
  const allPinned = sources.length > 0 && sources.every((source) => {
    const revision = currentRevision(source.source_id);
    return Boolean(revision?.object_key && revision.redistribution_decision && acceptedRights.has(revision.redistribution_decision));
  });
  const requiredWaivers = validation?.issues
    .filter((issue) => issue.waivable)
    .map((issue) => String(issue.evidence.waiver_id ?? ""))
    .filter(Boolean) ?? [];
  const mechanicalFailures = validation?.issues.filter(
    (issue) => !issue.waivable && issue.code !== "DW-OWNER-001",
  ) ?? [];
  const canPromote = Boolean(
    selected && validation && mechanicalFailures.length === 0 && version.trim() && reviewer.trim()
    && requiredWaivers.every((item) => accepted.includes(item)),
  );

  async function start(operation: "discover" | "fetch" | "compile", input: Record<string, unknown>) {
    setMessage(null);
    if (active) { setMessage({ key: "dataWorkbench.job.busy" }); return; }
    try {
      const response = await client.startJob(operation, input);
      setJob(response.job); setResumed(false); setCancelError(""); setFailures({ count: 0, error: "" }); setNow(Date.now());
      if (isActiveJob(response.job)) writeTrackedJob(browserStorage(), response.job.job_id);
    } catch (error) {
      setMessage(messageOf(error, "dataWorkbench.error.start"));
    }
  }

  function cancel(current: DataJob) {
    setCancelError("");
    client.cancelJob(current.job_id)
      .then((result) => { setJob(result.job); if (!isActiveJob(result.job)) writeTrackedJob(browserStorage(), null); })
      .catch((error) => setCancelError(showMessage(t, messageOf(error, "dataWorkbench.error.polling"))));
  }

  async function inspect(candidate: CandidateSummary) {
    setSelected(candidate); setValidation(null); setReview(null); setAccepted([]); setTab("candidates");
    try {
      const report = await client.validate(candidate.candidate_id);
      setValidation(report);
      setReview(await client.review(candidate.candidate_id));
    } catch (error) {
      setMessage(messageOf(error, "dataWorkbench.error.review"));
    }
  }

  async function promote() {
    if (!selected || !canPromote) return;
    try {
      await client.promote(selected.candidate_id, version.trim(), reviewer.trim(), accepted);
      setMessage({ key: "dataWorkbench.promoted" });
      await refresh();
      await onWorkspaceChanged?.();
    } catch (error) {
      setMessage(messageOf(error, "dataWorkbench.error.promote"));
    }
  }

  const operation = job ? job.operation.replaceAll("_", " ") : "";
  const status = job ? job.status.replaceAll("_", " ") : "";
  const seconds = job ? elapsedSeconds(job, now || Date.parse(job.updated_at ?? "") || 0) : null;
  const elapsed = seconds == null ? "—" : seconds < 60 ? t("dataWorkbench.job.seconds", { seconds }) : t("dataWorkbench.job.minutes", { minutes: Math.floor(seconds / 60), seconds: seconds % 60 });
  const percent = job ? progressPercent(job.progress) : 0;
  return <section className="data-workbench panel" aria-labelledby="data-workbench-title">
    <header className="data-workbench-head">
      <div><span>{t("dataWorkbench.eyebrow")}</span><h3 id="data-workbench-title">{t("dataWorkbench.title")}</h3><p>{t("dataWorkbench.intro")}</p><p className="data-workbench-expert">{t("dataWorkbench.expert")}</p></div>
      <span className="data-workbench-status">{job ? t("dataWorkbench.jobStatus", { operation: job.operation, status: job.status }) : t("dataWorkbench.idle")}</span>
    </header>
    {message && <p className="data-workbench-message" role="status">{showMessage(t, message)}</p>}
    {job && <div className={`data-job ${job.status}`} role="status">
      <div><b>{operation}</b><small>{job.error_code ? `${job.error_code}: ${job.error_message ?? t("dataWorkbench.job.failed")}` : status}</small>{resumed && <small>{t("dataWorkbench.job.resumed")}</small>}</div>
      <div className="data-job-progress"><progress max={100} value={percent} aria-label={t("dataWorkbench.job.progressAria", { operation })} /><small>{t("dataWorkbench.job.progress", { percent, elapsed })}</small></div>
      <div className="data-job-actions">
        {active && job.status !== "cancel_requested" && <Button size="sm" variant="ghost" onClick={() => cancel(job)}>{t("dataWorkbench.job.cancel")}</Button>}
        {job.status === "cancel_requested" && <small>{t("dataWorkbench.job.cancelling")}</small>}
        {!active && <Button size="sm" variant="ghost" onClick={() => { setJob(null); setResumed(false); }}>{t("dataWorkbench.job.dismiss")}</Button>}
      </div>
    </div>}
    {job && active && failures.count > 0 && !lost && <p className="data-workbench-message" role="status">{t("dataWorkbench.job.retrying", { error: failures.error, seconds: Math.round(pollDelay(failures.count) / 100) / 10 })}</p>}
    {job && active && lost && <p className="data-workbench-message" role="alert">{t("dataWorkbench.job.lost", { attempts: failures.count, error: failures.error })} <Button size="sm" onClick={() => setFailures({ count: 0, error: "" })}>{t("dataWorkbench.job.retry")}</Button></p>}
    {cancelError && <p className="data-workbench-message" role="alert">{t("dataWorkbench.job.cancelFailed", { error: cancelError })}</p>}
    <Tabs className="data-workbench-tabs" label={t("dataWorkbench.tabs")} value={tab} onChange={setTab} idBase="data-workbench" tabs={TABS.map((id) => ({ id, label: t(TAB_LABELS[id]) }))}>
      {tab === "overlays" && <OverlayEditor onWorkspaceChanged={onWorkspaceChanged} />}

      {tab === "installed" && <InstalledPacks bundles={bundles} />}

      {tab === "sources" && <OfficialSources sources={sources} currentRevision={currentRevision} busy={active} start={start} />}

      {tab === "build" && <BuildBenchmark pinnedCount={pinnedSources.length} sourceCount={sources.length} allPinned={allPinned} busy={active} start={start} />}

      {tab === "candidates" && <CandidateReview candidates={candidates} selected={selected} validation={validation} review={review} mechanicalFailures={mechanicalFailures} requiredWaivers={requiredWaivers} accepted={accepted} version={version} reviewer={reviewer} canPromote={canPromote} inspect={inspect} promote={promote} setAccepted={setAccepted} setVersion={setVersion} setReviewer={setReviewer} />}
    </Tabs>
  </section>;
}
